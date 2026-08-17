"""Serialización de dispositivos y notificaciones a consolas."""
from app.models import Device, Plan
from app.schemas.device import DevicePublic, DeviceSettings
from app.services.hub import hub


def default_settings_for_plan(plan: Plan) -> dict:
    bitrate_kbps = 4500 if plan.max_resolution == "1080p" else 2500
    return DeviceSettings(
        resolution=plan.max_resolution,
        fps=plan.max_fps,
        bitrate_kbps=bitrate_kbps,
        facing="back",
    ).model_dump()


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
