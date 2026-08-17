from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Device, PairingCode
from app.schemas import PairingClaimRequest, PairingClaimResponse
from app.security import generate_opaque_token, sha256_hex
from app.services.streaming import whip_url
from app.utils import ensure_aware, utcnow

router = APIRouter()


def _device_ws_url(request: Request, device_token: str) -> str:
    # request.base_url respeta X-Forwarded-Proto/Host (uvicorn corre con --proxy-headers).
    base = request.base_url
    scheme = "wss" if base.scheme == "https" else "ws"
    return f"{scheme}://{base.netloc}/api/v1/devices/ws?token={device_token}"


@router.post("/claim", response_model=PairingClaimResponse)
def claim_pairing_code(
    body: PairingClaimRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PairingClaimResponse:
    code = body.code.strip().upper()
    pairing = db.get(PairingCode, code)
    if pairing is None:
        raise HTTPException(status_code=404, detail="Código de emparejamiento inválido o expirado.")
    if pairing.used_at is not None:
        raise HTTPException(status_code=409, detail="El código de emparejamiento ya fue utilizado.")
    if ensure_aware(pairing.expires_at) < utcnow():
        raise HTTPException(status_code=404, detail="Código de emparejamiento inválido o expirado.")
    device = db.get(Device, pairing.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

    device_token = generate_opaque_token()
    device.device_token_hash = sha256_hex(device_token)
    device.platform = body.platform
    device.model = body.model.strip()
    pairing.used_at = utcnow()
    db.commit()

    return PairingClaimResponse(
        device_id=device.id,
        device_token=device_token,
        whip_url=whip_url(device.id),
        ws_url=_device_ws_url(request, device_token),
    )
