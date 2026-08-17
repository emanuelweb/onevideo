"""Canales WebSocket: dispositivo (control) y consola (dashboard)."""
import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select

# Se referencia el módulo (y no SessionLocal directo) para poder sustituir la
# fábrica de sesiones en tests.
from app import db as database
from app.models import Device, User
from app.models.device import DEVICE_STATUS_OFFLINE, DEVICE_STATUS_ONLINE, DEVICE_STATUS_STREAMING
from app.schemas.device import DeviceTelemetry
from app.security import decode_access_token, sha256_hex
from app.services.devices import device_status_message
from app.services.hub import hub
from app.utils import utcnow

logger = logging.getLogger("onevideo.ws")
router = APIRouter()

WS_POLICY_VIOLATION = 1008


def _find_device_id_by_token(token: str) -> uuid.UUID | None:
    with database.SessionLocal() as db:
        return db.scalar(select(Device.id).where(Device.device_token_hash == sha256_hex(token)))


def _resolve_console_user(token: str) -> uuid.UUID | None:
    sub = decode_access_token(token)
    if sub is None:
        return None
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        return None
    with database.SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None
    return user_id


async def _update_device_and_notify(
    device_id: uuid.UUID,
    *,
    status: str | None = None,
    camera_on: bool | None = None,
    touch: bool = False,
) -> None:
    with database.SessionLocal() as db:
        device = db.get(Device, device_id)
        if device is None:
            return
        if status is not None:
            device.status = status
        if camera_on is not None:
            device.camera_on = camera_on
        if touch:
            device.last_seen_at = utcnow()
        db.commit()
        user_id = device.user_id
        message = device_status_message(device)
    await hub.broadcast_to_user(user_id, message)


@router.websocket("/devices/ws")
async def device_ws(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    device_id = _find_device_id_by_token(token) if token else None
    if device_id is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    await websocket.accept()
    previous = await hub.register_device(device_id, websocket)
    if previous is not None:
        try:
            await previous.close(code=1000)
        except Exception:
            pass
    await _update_device_and_notify(device_id, status=DEVICE_STATUS_ONLINE, touch=True)

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except ValueError:
                # Mensaje no-JSON: se ignora.
                continue
            if not isinstance(message, dict):
                continue
            msg_type = message.get("type")
            payload = message.get("payload") or {}
            if msg_type == "status" and isinstance(payload, dict):
                try:
                    telemetry = DeviceTelemetry.model_validate(payload)
                except ValidationError:
                    logger.debug("Telemetría inválida de %s", device_id)
                    continue
                hub.set_telemetry(device_id, telemetry.model_dump())
                camera_on = bool(payload.get("camera_on", False))
                await _update_device_and_notify(
                    device_id,
                    status=DEVICE_STATUS_STREAMING if camera_on else DEVICE_STATUS_ONLINE,
                    camera_on=camera_on,
                    touch=True,
                )
            elif msg_type == "ack" and isinstance(payload, dict):
                logger.debug("Ack de %s: %s", device_id, payload)
    except WebSocketDisconnect:
        pass
    finally:
        removed = await hub.unregister_device(device_id, websocket)
        if removed:
            await _update_device_and_notify(device_id, status=DEVICE_STATUS_OFFLINE, touch=True)


@router.websocket("/console/ws")
async def console_ws(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    user_id = _resolve_console_user(token) if token else None
    if user_id is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    await websocket.accept()
    await hub.register_console(user_id, websocket)
    try:
        while True:
            # La consola no envía comandos por WS (usa REST); se ignora todo mensaje entrante.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unregister_console(user_id, websocket)
