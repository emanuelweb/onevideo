import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils import utcnow

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.plan import Plan

# Origen del plan activo. El plan es dato propio del usuario: la lógica de límites
# nunca depende de quién lo otorgó (hoy el admin, mañana una pasarela de pago).
PLAN_SOURCE_SIGNUP = "signup"
PLAN_SOURCE_ADMIN = "admin"
PLAN_SOURCE_STRIPE = "stripe"
PLAN_SOURCE_MERCADOPAGO = "mercadopago"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Se guarda siempre en minúsculas; unicidad case-insensitive.
    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    # Quién otorgó el plan activo: 'signup' | 'admin' | 'stripe' | 'mercadopago'.
    plan_source: Mapped[str] = mapped_column(Text, nullable=False, default=PLAN_SOURCE_SIGNUP)
    # NULL = sin vencimiento. Al vencer se degrada al plan gratuito (degradación perezosa).
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Marca de que el bootstrap automático de super-admin ya se resolvió para esta
    # cuenta (por promoción automática o por una revocación explícita). Mientras sea
    # NULL el bootstrap puede promover una vez; después nunca vuelve a tocarla, así
    # una revocación no se deshace sola en el siguiente inicio de sesión.
    superadmin_bootstrapped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    plan: Mapped["Plan"] = relationship("Plan", lazy="joined")
    devices: Mapped[list["Device"]] = relationship(
        "Device", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
