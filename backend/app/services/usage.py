"""Cálculo de horas de uso del mes calendario en curso."""
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import Row, func, or_, select
from sqlalchemy.orm import Session

from app.models import Device, StreamSession, User
from app.utils import ensure_aware, utcnow


def current_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or utcnow()
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _overlapping_sessions(
    db: Session,
    period_start: datetime,
    period_end: datetime,
    user_ids: Sequence[uuid.UUID] | None = None,
) -> Sequence[Row]:
    """Sesiones que se solapan con el período, con el dueño de cada dispositivo."""
    stmt = (
        select(Device.user_id, StreamSession.started_at, StreamSession.ended_at)
        .select_from(StreamSession)
        .join(Device, StreamSession.device_id == Device.id)
        .where(
            StreamSession.started_at < period_end,
            or_(StreamSession.ended_at.is_(None), StreamSession.ended_at > period_start),
        )
    )
    if user_ids is not None:
        stmt = stmt.where(Device.user_id.in_(user_ids))
    return db.execute(stmt).all()


def _clamped_seconds(
    started_at: datetime,
    ended_at: datetime | None,
    period_start: datetime,
    period_end: datetime,
    now: datetime,
) -> float:
    start = max(ensure_aware(started_at), period_start)
    end = min(ensure_aware(ended_at) or now, period_end)
    return (end - start).total_seconds() if end > start else 0.0


def hours_used(
    db: Session,
    user_id: uuid.UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> float:
    return hours_used_by_user(db, [user_id], period_start, period_end)[user_id]


def hours_used_by_user(
    db: Session,
    user_ids: Sequence[uuid.UUID],
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[uuid.UUID, float]:
    """Horas del período para varios usuarios en UNA sola consulta (evita el N+1)."""
    if not user_ids:
        return {}
    now = utcnow()
    if period_start is None or period_end is None:
        period_start, period_end = current_period(now)
    totals: dict[uuid.UUID, float] = {user_id: 0.0 for user_id in user_ids}
    for owner_id, started_at, ended_at in _overlapping_sessions(db, period_start, period_end, user_ids):
        if owner_id in totals:
            totals[owner_id] += _clamped_seconds(started_at, ended_at, period_start, period_end, now)
    return {user_id: round(seconds / 3600.0, 2) for user_id, seconds in totals.items()}


def hours_used_total(
    db: Session,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> float:
    """Horas del período sumando a todos los usuarios (panel de administración)."""
    now = utcnow()
    if period_start is None or period_end is None:
        period_start, period_end = current_period(now)
    total_seconds = sum(
        _clamped_seconds(started_at, ended_at, period_start, period_end, now)
        for _, started_at, ended_at in _overlapping_sessions(db, period_start, period_end)
    )
    return round(total_seconds / 3600.0, 2)


def has_hours_available(db: Session, user: User) -> bool:
    if user.plan.monthly_hours is None:
        return True
    return hours_used(db, user.id) < user.plan.monthly_hours


def usage_summary(db: Session, user: User) -> dict:
    period_start, period_end = current_period()
    used = hours_used(db, user.id, period_start, period_end)
    devices_used = db.scalar(select(func.count()).select_from(Device).where(Device.user_id == user.id)) or 0
    return {
        "period_start": period_start,
        "period_end": period_end,
        "hours_used": used,
        "hours_limit": user.plan.monthly_hours,
        "devices_used": devices_used,
        "devices_limit": user.plan.max_devices,
    }
