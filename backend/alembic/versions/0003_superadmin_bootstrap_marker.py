"""Marca de bootstrap de super-admin resuelto (una sola vez por cuenta).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-17

`superadmin_bootstrapped_at` deja constancia de que el bootstrap automático ya se
resolvió para esa cuenta (por promoción automática o por una revocación explícita
desde el panel o el CLI). Mientras sea NULL el bootstrap puede promover una vez;
después nunca vuelve a tocar la cuenta, así una revocación no se deshace sola en
el siguiente inicio de sesión.

Se aplica sobre una base con datos reales: la columna es NULL-able, de modo que
las cuentas existentes quedan disponibles para el bootstrap inicial.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("superadmin_bootstrapped_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Las cuentas que ya son super-admin quedan marcadas: nunca necesitan bootstrap.
    op.execute(
        "UPDATE users SET superadmin_bootstrapped_at = now() WHERE is_superadmin = true"
    )


def downgrade() -> None:
    op.drop_column("users", "superadmin_bootstrapped_at")
