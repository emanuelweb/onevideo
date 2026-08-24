"""Grabación en la nube: toggle por dispositivo, listado, descarga y borrado.

La descarga NO usa el header Authorization: el <video> del navegador no puede
mandar headers, así que va autenticada con un JWT de corta vida en el query
param `token`. Starlette FileResponse no soporta Range, por eso el soporte de
`Range: bytes=` está implementado a mano (streaming async por chunks de 512 KB).
"""
import asyncio
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Device, User
from app.schemas import (
    DevicePublic,
    DownloadTokenResponse,
    RecordingList,
    RecordingPublic,
    RecordingToggleRequest,
)
from app.services import mediamtx, recordings
from app.services.devices import device_public, notify_consoles

logger = logging.getLogger("onevideo.recordings")

router = APIRouter()

DOWNLOAD_CHUNK_BYTES = 512 * 1024
QUOTA_EXCEEDED_DETAIL = (
    "Alcanzaste el almacenamiento de grabaciones de tu plan. "
    "Elimina grabaciones o mejora tu plan."
)
NOT_FOUND_DETAIL = "Grabación no encontrada."

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _get_owned_device(db: Session, user: User, device_id: uuid.UUID) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    return device


def _user_device_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(Device.id).where(Device.user_id == user_id)))


def _usage_for_user(db: Session, user: User) -> tuple[int, int]:
    used = recordings.used_bytes_for_devices(_user_device_ids(db, user.id))
    return used, recordings.limit_bytes_for_plan(user.plan)


def _get_recording_path(device_id: uuid.UUID, rid: str) -> Path:
    path = recordings.resolve_recording_path(device_id, rid)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)
    return path


@router.post("/{device_id}/recording", response_model=DevicePublic)
async def toggle_recording(
    device_id: uuid.UUID,
    body: RecordingToggleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DevicePublic:
    device = _get_owned_device(db, current_user, device_id)
    if body.enabled:
        used_bytes, limit_bytes = _usage_for_user(db, current_user)
        if used_bytes >= limit_bytes:
            raise HTTPException(status_code=403, detail=QUOTA_EXCEEDED_DETAIL)
    device.recording_on = body.enabled
    db.commit()
    # Best-effort: si MediaMTX no responde, el estado ya quedó persistido y el
    # reconciliador del tracker lo aplicará en el siguiente ciclo.
    try:
        await mediamtx.set_recording(device.id, body.enabled)
    except Exception:
        logger.warning(
            "MediaMTX no respondió al cambiar la grabación del device %s; "
            "el reconciliador lo aplicará.",
            device.id,
        )
    await notify_consoles(device)
    return device_public(device)


@router.get("/{device_id}/recordings", response_model=RecordingList)
def list_device_recordings(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecordingList:
    device = _get_owned_device(db, current_user, device_id)
    used_bytes, limit_bytes = _usage_for_user(db, current_user)
    items = [RecordingPublic(**item) for item in recordings.list_recordings(device.id)]
    return RecordingList(items=items, used_bytes=used_bytes, limit_bytes=limit_bytes)


@router.post(
    "/{device_id}/recordings/{rid}/download-token", response_model=DownloadTokenResponse
)
def create_recording_download_token(
    device_id: uuid.UUID,
    rid: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadTokenResponse:
    device = _get_owned_device(db, current_user, device_id)
    _get_recording_path(device.id, rid)
    token, expires_at = recordings.create_download_token(current_user.id, device.id, rid)
    # URL absoluta desde el request: uvicorn corre con proxy-headers, así que
    # base_url ya respeta X-Forwarded-Proto/Host.
    base = str(request.base_url).rstrip("/")
    url = f"{base}/api/v1/devices/{device.id}/recordings/{rid}/download?token={token}"
    return DownloadTokenResponse(url=url, expires_at=expires_at)


async def _stream_file_range(path: Path, start: int, end: int):
    """Lee [start, end] del archivo en chunks de 512 KB sin bloquear el loop."""
    remaining = end - start + 1
    with path.open("rb") as file:
        file.seek(start)
        while remaining > 0:
            chunk = await asyncio.to_thread(file.read, min(DOWNLOAD_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{device_id}/recordings/{rid}/download")
async def download_recording(
    device_id: uuid.UUID,
    rid: str,
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    # Sin header Authorization: el <video> del navegador no puede mandar headers.
    payload = recordings.decode_download_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token de descarga inválido o expirado.")
    if payload.get("device_id") != str(device_id) or payload.get("rid") != rid:
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError:
        raise HTTPException(status_code=401, detail="Token de descarga inválido o expirado.")
    device = db.get(Device, device_id)
    if device is None or device.user_id != user_id:
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)

    path = _get_recording_path(device_id, rid)
    file_size = path.stat().st_size
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{path.name}"',
    }

    start, end, status_code = 0, file_size - 1, 200
    range_header = request.headers.get("range")
    match = RANGE_RE.match(range_header.strip()) if range_header else None
    start_text, end_text = match.groups() if match else ("", "")
    # Un Range no parseable ("bytes=abc", "bytes=-") se ignora y se responde 200
    # completo (RFC 7233 §3.1); el 416 queda solo para rangos bien formados
    # fuera del archivo.
    if start_text or end_text:
        if start_text:
            start = int(start_text)
            end = min(int(end_text), file_size - 1) if end_text else file_size - 1
        else:
            # Rango sufijo: los últimos N bytes.
            start = max(file_size - int(end_text), 0)
            end = file_size - 1
        if start >= file_size or start > end:
            headers["Content-Range"] = f"bytes */{file_size}"
            raise HTTPException(status_code=416, detail="Rango solicitado no disponible.", headers=headers)
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        _stream_file_range(path, start, end),
        status_code=status_code,
        headers=headers,
        media_type="video/mp4",
    )


@router.delete("/{device_id}/recordings/{rid}", status_code=204)
def delete_recording(
    device_id: uuid.UUID,
    rid: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    device = _get_owned_device(db, current_user, device_id)
    path = _get_recording_path(device.id, rid)
    if recordings.is_in_progress(path.stat().st_mtime):
        raise HTTPException(
            status_code=409,
            detail="Esa grabación está en curso. Detén la grabación antes de eliminarla.",
        )
    path.unlink(missing_ok=True)
    return Response(status_code=204)
