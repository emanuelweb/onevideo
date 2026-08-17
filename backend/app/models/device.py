import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import JSONType
from app.utils import utcnow

if TYPE_CHECKING:
    from app.models.pairing_code import PairingCode
    from app.models.stream_session import StreamSession
    from app.models.user import User

DEVICE_STATUS_ONLINE = "online"
DEVICE_STATUS_OFFLINE = "offline"
DEVICE_STATUS_STREAMING = "streaming"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    # sha256 hex del device_token; NULL hasta que la app reclama el pairing code.
    device_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    view_token: Mapped[str] = mapped_column(Text, nullable=False)
    camera_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=DEVICE_STATUS_OFFLINE)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="devices")
    pairing_codes: Mapped[list["PairingCode"]] = relationship(
        "PairingCode", back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
    stream_sessions: Mapped[list["StreamSession"]] = relationship(
        "StreamSession", back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
