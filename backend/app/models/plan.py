from decimal import Decimal

from sqlalchemy import Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONType


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_usd_month: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    max_devices: Mapped[int] = mapped_column(Integer, nullable=False)
    max_resolution: Mapped[str] = mapped_column(Text, nullable=False)
    max_fps: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL = horas ilimitadas (fair use).
    monthly_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
