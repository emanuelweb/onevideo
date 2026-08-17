"""Serialización de dispositivos, límites de calidad y notificaciones a consolas."""
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, Plan
from app.schemas.device import DevicePublic, DeviceSettings
from app.services.hub import hub

# Orden de las resoluciones soportadas, para comparar calidad contra el plan.
RESOLUTION_RANK = {"720p": 720, "1080p": 1080}


def default_settings_for_plan(plan: Plan) -> dict:
    bitrate_kbps = 4500 if plan.max_resolution == "1080p" else 2500
    return DeviceSettings(
        resolution=plan.max_resolution,
        fps=plan.max_fps,
        bitrate_kbps=bitrate_kbps,
        facing="back",
    ).model_dump()


def exceeds_plan(settings: DeviceSettings, plan: Plan) -> bool:
    return (
        RESOLUTION_RANK.get(settings.resolution, 0) > RESOLUTION_RANK.get(plan.max_resolution, 0)
        or settings.fps > plan.max_fps
    )


def clamp_settings_to_plan(settings: dict | None, plan: Plan) -> dict | None:
    """Devuelve los settings recortados al máximo del plan, o None si ya cabían."""
    try:
        current = DeviceSettings(**(settings or {}))
    except ValidationError:
        # Settings corruptos: se reemplazan por los del plan.
        return default_settings_for_plan(plan)
    if not exceeds_plan(current, plan):
        return None
    defaults = DeviceSettings(**default_settings_for_plan(plan))
    # Solo se recorta hacia abajo: nunca se sube la calidad de un dispositivo que ya
    # estaba por debajo del máximo del plan.
    keep_resolution = (
        RESOLUTION_RANK.get(current.resolution, 0) <= RESOLUTION_RANK.get(defaults.resolution, 0)
    )
    return DeviceSettings(
        resolution=current.resolution if keep_resolution else defaults.resolution,
        fps=min(current.fps, defaults.fps),
        bitrate_kbps=min(current.bitrate_kbps, defaults.bitrate_kbps),
        facing=current.facing,
    ).model_dump()


def clamp_user_devices_to_plan(db: Session, user_id: uuid.UUID, plan: Plan) -> list[uuid.UUID]:
    """Recorta la calidad guardada de los dispositivos del usuario al nuevo plan.

    El enforcement de calidad es cooperativo (docs/CONTRACT.md §8): el servidor no
    transcodifica. Si al vencer o bajar de plan se dejaran los settings en 1080p60,
    el celular seguiría publicando en esa calidad indefinidamente. No commitea: eso
    queda para quien llama, junto con el resto de su transacción.

    Devuelve los ids de los dispositivos ajustados, para avisarles con `set_quality`.
    """
    adjusted: list[uuid.UUID] = []
    devices = db.scalars(select(Device).where(Device.user_id == user_id)).all()
    for device in devices:
        clamped = clamp_settings_to_plan(device.settings, plan)
        if clamped is None:
            continue
        device.settings = clamped
        adjusted.append(device.id)
    return adjusted


async def push_quality_to_devices(db: Session, device_ids: list[uuid.UUID]) -> None:
    """Envía `set_quality` a los dispositivos conectados cuya calidad se recortó."""
    for device_id in device_ids:
        device = db.get(Device, device_id)
        if device is None:
            continue
        await hub.send_to_device(
            device_id,
            {
                "type": "command",
                "payload": {
                    "command_id": str(uuid.uuid4()),
                    "type": "set_quality",
                    "payload": DeviceSettings(**device.settings).model_dump(
                        include={"resolution", "fps", "bitrate_kbps"}
                    ),
                },
            },
        )
        await notify_consoles(device)


def device_public(device: Device) -> DevicePublic:
    return DevicePublic(
        id=device.id,
        name=device.name,
        platform=device.platform,
        model=device.model,
        status=device.status,
        camera_on=device.camera_on,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
        telemetry=hub.get_telemetry(device.id),
        settings=DeviceSettings(**(device.settings or {})),
    )


def device_status_message(device: Device) -> dict:
    return {"type": "device_status", "payload": {"device": device_public(device).model_dump(mode="json")}}


async def notify_consoles(device: Device) -> None:
    await hub.broadcast_to_user(device.user_id, device_status_message(device))
