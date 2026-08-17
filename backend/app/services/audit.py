"""Rastro de auditoría de las acciones sensibles del panel de administración.

Las asignaciones de plan ya quedan auditadas en la tabla `plan_grants` (quién, cuándo,
nota). Los cambios de privilegio/estado y la eliminación de cuentas no tienen tabla
propia, así que se registran aquí como log estructurado con el mismo criterio: qué
administrador, sobre qué cuenta, qué campo, valor anterior y valor nuevo.

Sale por el logger `onevideo.audit`, que en el contenedor va a la salida estándar y
queda recogido por `docker logs` / el agregador de logs del VPS.
"""
import logging
import uuid
from typing import Any

from app.models import User

logger = logging.getLogger("onevideo.audit")


def _fields(admin: User, target: User) -> str:
    return (
        f"admin_id={admin.id} admin_email={admin.email} "
        f"user_id={target.id} user_email={target.email}"
    )


def log_user_field_change(admin: User, target: User, field: str, before: Any, after: Any) -> None:
    """Registra el cambio de un campo sensible (is_superadmin, is_active)."""
    logger.info(
        "cambio_de_usuario %s campo=%s antes=%s despues=%s",
        _fields(admin, target),
        field,
        before,
        after,
    )


def log_user_deleted(admin: User, target: User, device_ids: list[uuid.UUID]) -> None:
    """Deja constancia del borrado antes de que la fila (y su cascada) desaparezca."""
    logger.warning(
        "eliminacion_de_usuario %s dispositivos=%s era_superadmin=%s",
        _fields(admin, target),
        ",".join(str(device_id) for device_id in device_ids) or "-",
        target.is_superadmin,
    )


def log_plan_assigned(
    admin: User, target: User, plan_code: str, expires_at: Any, adjusted_devices: int
) -> None:
    """Complementa a `plan_grants` con el efecto colateral sobre los dispositivos."""
    logger.info(
        "asignacion_de_plan %s plan=%s vence=%s dispositivos_ajustados=%s",
        _fields(admin, target),
        plan_code,
        expires_at.isoformat() if expires_at is not None else "-",
        adjusted_devices,
    )
