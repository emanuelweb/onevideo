import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils import utcnow

if TYPE_CHECKING:
    from app.models.plan import Plan
    from app.models.user import User

# BIGSERIAL en PostgreSQL; en SQLite solo "INTEGER PRIMARY KEY" es autoincremental.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class PlanGrant(Base):
    """Auditoría de asignaciones de plan (admin hoy, pasarelas de pago mañana)."""

    __tablename__ = "plan_grants"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    # NULL = otorgado automáticamente (webhook de una pasarela de pago).
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 'admin' | 'stripe' | 'mercadopago'.
    source: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    plan: Mapped["Plan"] = relationship("Plan", lazy="joined")
    granted_by_user: Mapped["User | None"] = relationship(
        "User", lazy="joined", foreign_keys=[granted_by]
    )
