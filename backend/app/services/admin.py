"""Bootstrap del primer super-admin, sin entrar al contenedor y sin escalada de privilegios.

El bootstrap exige **dos** cosas al mismo tiempo:

1. que el correo de la cuenta esté en `SUPERADMIN_EMAILS`, y
2. que la petición traiga el secreto `SUPERADMIN_BOOTSTRAP_TOKEN` en el campo
   `bootstrap_token` del cuerpo de `/auth/register` o `/auth/login`.

El secreto es imprescindible: el correo del operador suele ser público, así que
comparar solo la cadena de correo dejaría que cualquiera que se registre antes que
su dueño legítimo quede como administrador. El secreto solo lo conoce quien puede
editar las variables de entorno del despliegue, que es exactamente quien debe poder
crear al primer administrador.

Además el bootstrap actúa **una sola vez por cuenta**: al promover (o al revocar el
rol a mano desde el panel o el CLI) se marca `superadmin_bootstrapped_at`, de modo
que una revocación no se deshace sola en el siguiente inicio de sesión.
"""
import logging
import secrets

from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.utils import utcnow

logger = logging.getLogger("onevideo.admin")


def is_bootstrap_email(email: str) -> bool:
    """True si el correo figura en SUPERADMIN_EMAILS (case-insensitive)."""
    return email.strip().lower() in settings.superadmin_emails_list


def mark_bootstrap_resolved(user: User) -> None:
    """Cierra el bootstrap automático de la cuenta (no commitea).

    Se llama al promover automáticamente y en cada cambio manual del rol, para que
    el bootstrap nunca vuelva a promover una cuenta cuyo rol ya decidió un humano.
    """
    if user.superadmin_bootstrapped_at is None:
        user.superadmin_bootstrapped_at = utcnow()


def ensure_bootstrap_superadmin(
    db: Session, user: User, bootstrap_token: str | None = None
) -> bool:
    """Promueve al usuario si su correo está autorizado y el secreto coincide.

    Idempotente: devuelve True solo cuando hubo una promoción efectiva.
    """
    if user.is_superadmin or user.superadmin_bootstrapped_at is not None:
        return False
    if not is_bootstrap_email(user.email):
        return False

    expected = settings.superadmin_bootstrap_token.strip()
    provided = (bootstrap_token or "").strip()
    if not expected:
        logger.warning(
            "Bootstrap de super-admin ignorado para %s: falta configurar "
            "SUPERADMIN_BOOTSTRAP_TOKEN.",
            user.email,
        )
        return False
    # Comparación en tiempo constante: el secreto viaja en el cuerpo de la petición.
    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning(
            "Intento de bootstrap de super-admin con secreto inválido para %s.", user.email
        )
        return False

    user.is_superadmin = True
    mark_bootstrap_resolved(user)
    db.commit()
    logger.info("Bootstrap de super-admin aplicado a %s.", user.email)
    return True
