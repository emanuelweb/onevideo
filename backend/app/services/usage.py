"""Cálculo de horas de uso del mes calendario en curso."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
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


def hours_used(
    db: Session,
    user_id: uuid.UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> float:
    now = utcnow()
    if period_start is None or period_end is None:
        period_start, period_end = current_period(now)
    rows = db.execute(
        select(StreamSession.started_at, StreamSession.ended_at)
        .join(Device, StreamSession.device_id == Device.id)
        .where(
            Device.user_id == user_id,
            StreamSession.started_at < period_end,
            or_(StreamSession.ended_at.is_(None), StreamSession.ended_at > period_start),
        )
    ).all()
    total_seconds = 0.0
    for started_at, ended_at in rows:
        start = max(ensure_aware(started_at), period_start)
        end = min(ensure_aware(ended_at) or now, period_end)
        if end > start:
            total_seconds += (end - start).total_seconds()
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
