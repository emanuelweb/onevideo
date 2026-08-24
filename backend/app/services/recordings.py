"""Grabaciones en la nube: archivos MP4 en disco, rids base64url y tokens de descarga.

MediaMTX escribe los segmentos en `<RECORDINGS_DIR>/live/<device_uuid>/` con el
nombre `%Y-%m-%d_%H-%M-%S-%f.mp4` (UTC). El `rid` público es el filename en
base64url SIN padding; al decodificarlo se valida contra un patrón estricto y el
path final debe resolverse DENTRO del directorio del dispositivo (defensa de
path traversal con resolve() + relative_to).
"""
import base64
import binascii
import re
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from app.config import settings
from app.models import Plan
from app.security import JWT_ALGORITHM
from app.utils import utcnow

# Nombre de archivo permitido: sin separadores, sin rutas absolutas, extensión .mp4.
FILENAME_RE = re.compile(r"^[0-9A-Za-z_\-\.]+\.mp4$")
# Formato de timestamp con el que MediaMTX nombra cada segmento.
FILENAME_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S-%f"
# Un archivo con mtime más reciente que esto se considera todavía en escritura.
IN_PROGRESS_WINDOW_SECONDS = 30
DOWNLOAD_TOKEN_SCOPE = "recording"
DOWNLOAD_TOKEN_TTL_HOURS = 6


def device_recordings_dir(device_id: uuid.UUID) -> Path:
    return Path(settings.recordings_dir) / "live" / str(device_id)


def encode_rid(filename: str) -> str:
    return base64.urlsafe_b64encode(filename.encode("utf-8")).decode("ascii").rstrip("=")


def decode_rid(rid: str) -> str | None:
    """Decodifica el rid a filename, o None si no es un nombre de grabación válido."""
    try:
        padded = rid + "=" * (-len(rid) % 4)
        filename = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error):
        return None
    if not FILENAME_RE.match(filename) or ".." in filename:
        return None
    return filename


def resolve_recording_path(device_id: uuid.UUID, rid: str) -> Path | None:
    """Path absoluto de la grabación, garantizado dentro del directorio del device."""
    filename = decode_rid(rid)
    if filename is None:
        return None
    base = device_recordings_dir(device_id).resolve()
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def parse_started_at(filename: str) -> datetime | None:
    stem = filename[: -len(".mp4")]
    try:
        return datetime.strptime(stem, FILENAME_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_in_progress(mtime: float) -> bool:
    return utcnow().timestamp() - mtime < IN_PROGRESS_WINDOW_SECONDS


def list_recordings(device_id: uuid.UUID) -> list[dict]:
    """Grabaciones del dispositivo (más reciente primero), como dicts serializables."""
    directory = device_recordings_dir(device_id)
    if not directory.is_dir():
        return []
    items: list[dict] = []
    for path in directory.iterdir():
        if not path.is_file() or not FILENAME_RE.match(path.name):
            continue
        stat = path.stat()
        items.append(
            {
                "id": encode_rid(path.name),
                "filename": path.name,
                "started_at": parse_started_at(path.name),
                "size_bytes": stat.st_size,
                "in_progress": is_in_progress(stat.st_mtime),
            }
        )
    items.sort(key=lambda item: item["filename"], reverse=True)
    return items


def used_bytes_for_devices(device_ids: Iterable[uuid.UUID]) -> int:
    """Bytes ocupados por las grabaciones de los dispositivos dados (cuota por usuario)."""
    total = 0
    for device_id in device_ids:
        directory = device_recordings_dir(device_id)
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_file() and FILENAME_RE.match(path.name):
                total += path.stat().st_size
    return total


def limit_bytes_for_plan(plan: Plan) -> int:
    return plan.max_recording_gb * 1024**3


def create_download_token(
    user_id: uuid.UUID, device_id: uuid.UUID, rid: str
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=DOWNLOAD_TOKEN_TTL_HOURS)
    payload = {
        "sub": str(user_id),
        "scope": DOWNLOAD_TOKEN_SCOPE,
        "device_id": str(device_id),
        "rid": rid,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM), expires_at


def decode_download_token(token: str) -> dict | None:
    """Claims del token de descarga si es válido, no expiró y tiene el scope correcto."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("scope") != DOWNLOAD_TOKEN_SCOPE:
        return None
    return payload
