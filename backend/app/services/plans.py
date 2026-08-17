"""Resolución del plan efectivo de un usuario (degradación perezosa al vencer)."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan, User
from app.models.user import PLAN_SOURCE_SIGNUP
from app.services.devices import clamp_user_devices_to_plan
from app.utils import ensure_aware, utcnow

logger = logging.getLogger("onevideo.plans")

FREE_PLAN_CODE = "free"


def resolve_effective_plan(db: Session, user: User) -> Plan:
    """Devuelve el plan vigente del usuario, degradándolo si ya venció.

    El vencimiento se aplica de forma perezosa (sin tareas programadas): la primera
    vez que el usuario aparece después de la fecha, se lo baja al plan gratuito y se
    persiste. El resto del código sigue usando `user.plan` sin enterarse.
    """
    expires_at = ensure_aware(user.plan_expires_at)
    if expires_at is None or expires_at > utcnow():
        return user.plan

    free_plan = db.scalar(select(Plan).where(Plan.code == FREE_PLAN_CODE))
    if free_plan is None:
        # Sin plan gratuito configurado no hay a dónde degradar: se conserva el actual.
        return user.plan

    user.plan = free_plan
    user.plan_id = free_plan.id
    user.plan_source = PLAN_SOURCE_SIGNUP
    user.plan_expires_at = None
    # La calidad guardada de los dispositivos también baja: el enforcement es
    # cooperativo, así que dejarla en 1080p60 los mantendría publicando en esa
    # calidad para siempre.
    adjusted = clamp_user_devices_to_plan(db, user.id, free_plan)
    db.commit()
    if adjusted:
        logger.info(
            "Plan vencido: %s dispositivo(s) de %s ajustados al plan gratuito.",
            len(adjusted),
            user.email,
        )
    return free_plan
