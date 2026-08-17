"""Emisión de códigos de emparejamiento (un solo uso, 15 minutos)."""
import uuid
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import PairingCode
from app.security import PAIRING_CODE_TTL_MINUTES, generate_pairing_code
from app.utils import utcnow


def issue_pairing_code(db: Session, device_id: uuid.UUID) -> PairingCode:
    """Crea un código nuevo e invalida los anteriores no usados del dispositivo."""
    db.execute(
        delete(PairingCode).where(PairingCode.device_id == device_id, PairingCode.used_at.is_(None))
    )
    for _ in range(10):
        code = generate_pairing_code()
        if db.get(PairingCode, code) is None:
            pairing = PairingCode(
                code=code,
                device_id=device_id,
                expires_at=utcnow() + timedelta(minutes=PAIRING_CODE_TTL_MINUTES),
            )
            db.add(pairing)
            return pairing
    raise RuntimeError("No se pudo generar un código de emparejamiento único")
