"""Panel de super-administración: usuarios, planes y auditoría de asignaciones."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_superadmin
from app.models import Device, Plan, PlanGrant, User
from app.models.device import DEVICE_STATUS_STREAMING
from app.models.user import PLAN_SOURCE_ADMIN
from app.schemas import (
    AdminPlanAssign,
    AdminPlanCount,
    AdminStats,
    AdminUser,
    AdminUserList,
    AdminUserUpdate,
    PlanGrantPublic,
    PlanPublic,
)
from app.services.admin import is_bootstrap_email, mark_bootstrap_resolved
from app.services.audit import log_plan_assigned, log_user_deleted, log_user_field_change
from app.services.devices import clamp_user_devices_to_plan, push_quality_to_devices
from app.services.hub import hub
from app.services.usage import current_period, hours_used, hours_used_by_user, hours_used_total
from app.utils import ensure_aware, utcnow

router = APIRouter()

logger = logging.getLogger("onevideo.admin")

SELF_LOCKOUT_DETAIL = "No puedes quitarte a ti mismo los permisos de administrador."
SELF_DEACTIVATE_DETAIL = "No puedes desactivar tu propia cuenta."
SELF_DELETE_DETAIL = "No puedes eliminar tu propia cuenta."


def _escape_like(term: str) -> str:
    """Neutraliza los comodines de LIKE para que la búsqueda sea literal."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


def _apply_search(stmt: Select, search: str | None) -> Select:
    if not search or not search.strip():
        return stmt
    pattern = _escape_like(search.strip())
    return stmt.where(
        or_(
            func.lower(User.email).like(pattern, escape="\\"),
            func.lower(User.name).like(pattern, escape="\\"),
        )
    )


def _get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return user


def _devices_count(db: Session, user_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Device).where(Device.user_id == user_id)) or 0


def _device_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(Device.id).where(Device.user_id == user_id)).all())


async def _close_user_connections(db: Session, user: User) -> None:
    """Corta los WebSocket vivos del usuario (igual que DELETE /devices/{id}).

    Sin esto, tras eliminar o desactivar la cuenta el celular seguiría conectado y
    publicando en MediaMTX hasta que el hook de auth lo rechace en la siguiente
    publicación, dejando un stream huérfano al aire.
    """
    for device_id in _device_ids(db, user.id):
        await hub.close_device(device_id)


def _admin_user(user: User, devices_count: int, hours_used_month: float) -> AdminUser:
    return AdminUser(
        id=user.id,
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        is_superadmin=user.is_superadmin,
        created_at=user.created_at,
        plan=PlanPublic.model_validate(user.plan),
        plan_source=user.plan_source,
        plan_expires_at=user.plan_expires_at,
        devices_count=devices_count,
        hours_used_month=hours_used_month,
    )


def _admin_user_detail(db: Session, user: User) -> AdminUser:
    return _admin_user(user, _devices_count(db, user.id), hours_used(db, user.id))


@router.get("/stats", response_model=AdminStats)
def get_stats(
    _admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
) -> AdminStats:
    period_start, period_end = current_period()
    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    users_active = (
        db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    )
    devices_total = db.scalar(select(func.count()).select_from(Device)) or 0
    devices_streaming = (
        db.scalar(
            select(func.count()).select_from(Device).where(Device.status == DEVICE_STATUS_STREAMING)
        )
        or 0
    )
    # Un solo GROUP BY para todos los planes (incluye los que no tienen usuarios).
    plan_rows = db.execute(
        select(Plan.code, Plan.name, func.count(User.id))
        .select_from(Plan)
        .outerjoin(User, User.plan_id == Plan.id)
        .group_by(Plan.id, Plan.code, Plan.name, Plan.sort_order)
        .order_by(Plan.sort_order)
    ).all()
    return AdminStats(
        users_total=users_total,
        users_active=users_active,
        devices_total=devices_total,
        devices_streaming=devices_streaming,
        hours_this_month=hours_used_total(db, period_start, period_end),
        users_by_plan=[
            AdminPlanCount(plan_code=code, plan_name=name, count=count)
            for code, name, count in plan_rows
        ],
    )


@router.get("/users", response_model=AdminUserList)
def list_users(
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
) -> AdminUserList:
    total = db.scalar(_apply_search(select(func.count()).select_from(User), search)) or 0

    # Conteo de dispositivos como agregado en la misma consulta: nada de un query por usuario.
    devices_by_user = (
        select(Device.user_id.label("user_id"), func.count(Device.id).label("devices_count"))
        .group_by(Device.user_id)
        .subquery()
    )
    stmt = _apply_search(
        select(User, func.coalesce(devices_by_user.c.devices_count, 0)).outerjoin(
            devices_by_user, devices_by_user.c.user_id == User.id
        ),
        search,
    )
    rows = db.execute(
        stmt.order_by(User.created_at.desc(), User.id).limit(limit).offset(offset)
    ).all()

    # Las horas del mes de toda la página se resuelven en una sola consulta.
    hours_by_user = hours_used_by_user(db, [user.id for user, _ in rows])
    return AdminUserList(
        total=total,
        items=[
            _admin_user(user, devices_count, hours_by_user.get(user.id, 0.0))
            for user, devices_count in rows
        ],
    )


@router.get("/users/{user_id}", response_model=AdminUser)
def get_user(
    user_id: uuid.UUID,
    _admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
) -> AdminUser:
    return _admin_user_detail(db, _get_user(db, user_id))


@router.post("/users/{user_id}/plan", response_model=AdminUser)
async def assign_plan(
    user_id: uuid.UUID,
    body: AdminPlanAssign,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
) -> AdminUser:
    user = _get_user(db, user_id)
    plan = db.scalar(select(Plan).where(Plan.code == body.plan_code.strip().lower()))
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan no encontrado.")
    expires_at = ensure_aware(body.expires_at)
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status_code=422, detail="La fecha de vencimiento debe ser futura.")

    note = body.note.strip() if body.note and body.note.strip() else None
    # La auditoría se escribe SIEMPRE; mañana una pasarela de pago hará lo mismo
    # con source='stripe'/'mercadopago' y granted_by=NULL.
    db.add(
        PlanGrant(
            user_id=user.id,
            plan_id=plan.id,
            granted_by=admin.id,
            source=PLAN_SOURCE_ADMIN,
            expires_at=expires_at,
            note=note,
        )
    )
    user.plan = plan
    user.plan_id = plan.id
    user.plan_source = PLAN_SOURCE_ADMIN
    user.plan_expires_at = expires_at
    # Bajar de plan también recorta la calidad ya configurada en los dispositivos:
    # el enforcement es cooperativo, así que hay que reescribirla y avisarles.
    adjusted = clamp_user_devices_to_plan(db, user.id, plan)
    db.commit()
    log_plan_assigned(admin, user, plan.code, expires_at, len(adjusted))
    await push_quality_to_devices(db, adjusted)
    return _admin_user_detail(db, user)


@router.patch("/users/{user_id}", response_model=AdminUser)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
) -> AdminUser:
    user = _get_user(db, user_id)
    is_self = user.id == admin.id
    if is_self and body.is_superadmin is False:
        raise HTTPException(status_code=409, detail=SELF_LOCKOUT_DETAIL)
    if is_self and body.is_active is False:
        raise HTTPException(status_code=409, detail=SELF_DEACTIVATE_DETAIL)

    deactivated = body.is_active is False and user.is_active
    if body.is_active is not None and body.is_active != user.is_active:
        log_user_field_change(admin, user, "is_active", user.is_active, body.is_active)
        user.is_active = body.is_active
    if body.is_superadmin is not None:
        if body.is_superadmin != user.is_superadmin:
            log_user_field_change(
                admin, user, "is_superadmin", user.is_superadmin, body.is_superadmin
            )
            user.is_superadmin = body.is_superadmin
        # El rol pasó por una decisión humana: el bootstrap automático no vuelve a
        # tocar esta cuenta, para que una revocación no se deshaga en el próximo login.
        mark_bootstrap_resolved(user)
        if body.is_superadmin is False and is_bootstrap_email(user.email):
            logger.warning(
                "Se revocó el rol de administrador a %s, pero su correo sigue en "
                "SUPERADMIN_EMAILS: conviene quitarlo de la variable de entorno.",
                user.email,
            )
    db.commit()
    if deactivated:
        await _close_user_connections(db, user)
    return _admin_user_detail(db, user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
) -> Response:
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=409, detail=SELF_DELETE_DETAIL)
    # El borrado es duro y arrastra dispositivos e historial: queda constancia antes.
    log_user_deleted(admin, user, _device_ids(db, user.id))
    await _close_user_connections(db, user)
    db.delete(user)
    db.commit()
    return Response(status_code=204)


@router.get("/users/{user_id}/grants", response_model=list[PlanGrantPublic])
def list_grants(
    user_id: uuid.UUID,
    _admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
) -> list[PlanGrantPublic]:
    user = _get_user(db, user_id)
    grants = db.scalars(
        select(PlanGrant)
        .where(PlanGrant.user_id == user.id)
        .order_by(PlanGrant.created_at.desc(), PlanGrant.id.desc())
    ).all()
    return [
        PlanGrantPublic(
            id=grant.id,
            plan_code=grant.plan.code,
            plan_name=grant.plan.name,
            source=grant.source,
            granted_by_email=grant.granted_by_user.email if grant.granted_by_user else None,
            expires_at=grant.expires_at,
            note=grant.note,
            created_at=grant.created_at,
        )
        for grant in grants
    ]
