"""Construcción de URLs de streaming (WHIP/WHEP/player) según el contrato."""
import uuid

from app.config import settings
from app.models import Device
from app.schemas.device import StreamInfo


def stream_base_url() -> str:
    return settings.stream_public_url.rstrip("/")


def whip_url(device_id: uuid.UUID) -> str:
    return f"{stream_base_url()}/live/{device_id}/whip"


def build_stream_info(device: Device) -> StreamInfo:
    base = stream_base_url()
    path = f"live/{device.id}"
    return StreamInfo(
        whip_url=f"{base}/{path}/whip",
        whep_url=f"{base}/{path}/whep?token={device.view_token}",
        player_url=f"{base}/{path}?token={device.view_token}",
        view_token=device.view_token,
    )
