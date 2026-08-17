"""Utilidades de seguridad: contraseñas (bcrypt), JWT (HS256) y tokens opacos."""
import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

JWT_ALGORITHM = "HS256"
BCRYPT_ROUNDS = 12
# bcrypt solo considera los primeros 72 bytes de la contraseña.
_BCRYPT_MAX_BYTES = 72

PAIRING_CODE_ALPHABET = string.ascii_uppercase + string.digits
PAIRING_CODE_LENGTH = 8
PAIRING_CODE_TTL_MINUTES = 15


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, expires_minutes: int | None = None) -> str:
    minutes = settings.access_token_expire_minutes if expires_minutes is None else expires_minutes
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Devuelve el claim `sub` si el token es válido y no expiró; si no, None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


def generate_opaque_token() -> str:
    """Token opaco urlsafe de 43 caracteres (device_token / view_token)."""
    return secrets.token_urlsafe(32)


def generate_pairing_code() -> str:
    return "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
