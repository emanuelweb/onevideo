"""CLI de respaldo para administrar super-admins sin tocar la base a mano.

Uso dentro del contenedor del API:

    docker exec <contenedor-api> python scripts/manage.py promote correo@ejemplo.com
    docker exec <contenedor-api> python scripts/manage.py demote correo@ejemplo.com
    docker exec <contenedor-api> python scripts/manage.py list-admins

Es la vía más directa cuando se tiene acceso al contenedor. La alternativa sin exec
es el bootstrap por variables de entorno (SUPERADMIN_EMAILS + SUPERADMIN_BOOTSTRAP_TOKEN,
ver app/services/admin.py).

Tanto `promote` como `demote` cierran el bootstrap automático de la cuenta: una vez
que un humano decidió el rol, la variable de entorno ya no lo cambia.
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services.admin import is_bootstrap_email, mark_bootstrap_resolved  # noqa: E402


def _find_user(db, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def _warn_if_still_in_env(user: User) -> None:
    if is_bootstrap_email(user.email):
        print(
            f"Aviso: {user.email} sigue en SUPERADMIN_EMAILS. El bootstrap automático ya no "
            "volverá a promover esta cuenta, pero conviene quitar el correo de la variable "
            "de entorno para evitar confusiones."
        )


def _set_superadmin(email: str, value: bool) -> int:
    with SessionLocal() as db:
        user = _find_user(db, email)
        if user is None:
            print(f"No existe una cuenta con el correo {email}.", file=sys.stderr)
            return 1
        cambio = user.is_superadmin != value
        user.is_superadmin = value
        # El rol pasó por una decisión humana: el bootstrap automático no vuelve a
        # tocar esta cuenta (si no, la revocación se desharía en el próximo login).
        mark_bootstrap_resolved(user)
        db.commit()
        if not cambio:
            estado = "ya es administrador" if value else "ya no era administrador"
            print(f"{user.email} {estado}. Sin cambios.")
        else:
            accion = "promovido a administrador" if value else "removido de administrador"
            print(f"{user.email} {accion}.")
        if not value:
            _warn_if_still_in_env(user)
        return 0


def _list_admins() -> int:
    with SessionLocal() as db:
        admins = db.scalars(
            select(User).where(User.is_superadmin.is_(True)).order_by(User.created_at)
        ).all()
        if not admins:
            print("No hay administradores configurados.")
            return 0
        print(f"Administradores ({len(admins)}):")
        for admin in admins:
            estado = "activo" if admin.is_active else "inactivo"
            print(f"  - {admin.email} ({admin.name}) [{estado}]")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="manage.py", description="Administración de super-admins de OneVideo."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote = subparsers.add_parser("promote", help="Otorga permisos de administrador a un correo.")
    promote.add_argument("email", help="Correo de la cuenta.")

    demote = subparsers.add_parser("demote", help="Quita permisos de administrador a un correo.")
    demote.add_argument("email", help="Correo de la cuenta.")

    subparsers.add_parser("list-admins", help="Lista las cuentas con permisos de administrador.")

    args = parser.parse_args(argv)
    if args.command == "promote":
        return _set_superadmin(args.email, True)
    if args.command == "demote":
        return _set_superadmin(args.email, False)
    return _list_admins()


if __name__ == "__main__":
    raise SystemExit(main())
