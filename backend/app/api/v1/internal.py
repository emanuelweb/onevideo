"""Hook de autenticación externa de MediaMTX (solo red interna de Docker)."""
import ipaddress
import uuid
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Device
from app.schemas import MediaMTXAuthPayload
from app.security import constant_time_equals, sha256_hex
from app.services.plans import resolve_effective_plan
from app.services.usage import has_hours_available
from app.utils import is_internal_ip

router = APIRouter()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def _require_internal_caller(request: Request) -> None:
    """Autentica que el llamante sea MediaMTX (u otro componente interno).

    Con MEDIAMTX_AUTH_SECRET configurado (producción), se exige que la URL del hook
    incluya `?secret=<valor>`: MediaMTX lo envía porque docker-compose se lo inyecta
    en MTX_AUTHHTTPADDRESS. Esto no depende de la IP del cliente, que es falsificable
    cuando uvicorn corre con --proxy-headers --forwarded-allow-ips "*" detrás de
    Traefik (X-Forwarded-For lo controla el cliente).

    Sin secreto (dev/tests), se exige al menos que la IP del cliente sea
    privada/loopback.
    """
    secret = settings.mediamtx_auth_secret
    if secret:
        provided = request.query_params.get("secret") or ""
        if not constant_time_equals(provided, secret):
            raise _unauthorized("Origen no autorizado.")
        return
    client = request.client
    if client is None:
        return
    try:
        ip = ipaddress.ip_address(client.host)
    except ValueError:
        # Host no-IP (p. ej. TestClient): se asume entorno local.
        return
    if not (ip.is_private or ip.is_loopback):
        raise _unauthorized("Origen no autorizado.")


def _resolve_device(db: Session, path: str | None) -> Device:
    if not path or not path.startswith("live/"):
        raise _unauthorized("Ruta de stream inválida.")
    try:
        device_id = uuid.UUID(path.split("/", 1)[1])
    except ValueError:
        raise _unauthorized("Ruta de stream inválida.")
    device = db.get(Device, device_id)
    if device is None:
        raise _unauthorized("Dispositivo no encontrado.")
    return device


def _extract_bearer(body: MediaMTXAuthPayload) -> str | None:
    # MediaMTX pasa el header Authorization como token o como password según el cliente.
    for candidate in (body.token, body.password):
        if not candidate:
            continue
        value = candidate.strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        if value:
            return value
    return None


def _extract_query_token(query: str | None) -> str | None:
    if not query:
        return None
    values = parse_qs(query).get("token")
    return values[0] if values else None


@router.post("/mediamtx/auth")
def mediamtx_auth(
    body: MediaMTXAuthPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    _require_internal_caller(request)

    if body.action == "publish":
        device = _resolve_device(db, body.path)
        token = _extract_bearer(body)
        if (
            not token
            or not device.device_token_hash
            or not constant_time_equals(sha256_hex(token), device.device_token_hash)
        ):
            raise _unauthorized("Token de dispositivo inválido.")
        owner = device.user
        if owner is None or not owner.is_active:
            raise _unauthorized("Usuario inactivo.")
        # La publicación del celular no pasa por get_current_user: se aplica aquí
        # la degradación perezosa antes de medir las horas contra el plan.
        resolve_effective_plan(db, owner)
        if not has_hours_available(db, owner):
            raise _unauthorized("Alcanzaste el límite de horas de tu plan este mes.")
        return {"detail": "ok"}

    if body.action == "read":
        device = _resolve_device(db, body.path)
        token = _extract_query_token(body.query)
        if not token or not constant_time_equals(token, device.view_token):
            raise _unauthorized("Token de visualización inválido.")
        return {"detail": "ok"}

    # "api" y otros orígenes internos.
    if settings.mediamtx_auth_secret:
        # El secreto ya autenticó al llamante como MediaMTX; body.ip no es confiable
        # (lo controla quien envía el payload) y no se usa como criterio.
        return {"detail": "ok"}
    # Sin secreto (dev/tests): comportamiento previo basado en la IP reportada.
    if body.ip and is_internal_ip(body.ip):
        return {"detail": "ok"}
    raise _unauthorized("Origen no autorizado.")
