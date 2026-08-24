"""Grabación en la nube: toggle por dispositivo y cuota de almacenamiento por plan.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-24

Se aplica sobre una base con datos reales: las columnas nuevas son NOT NULL con
server_default, de modo que las filas existentes se rellenan solas (dispositivos
sin grabar y 1 GB de cuota hasta que el seed la ajuste por plan).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cuota de grabaciones y línea de features por plan.
RECORDING_QUOTAS = [
    ("free", 1),
    ("creator", 5),
    ("pro", 20),
    ("studio", 40),
]


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("recording_on", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "plans",
        sa.Column("max_recording_gb", sa.Integer(), nullable=False, server_default="1"),
    )
    for code, gb in RECORDING_QUOTAS:
        feature = f"{gb} GB de grabaciones en la nube"
        op.execute(
            f"UPDATE plans SET max_recording_gb = {gb}, "
            f"features = features || '[\"{feature}\"]'::jsonb "
            f"WHERE code = '{code}'"
        )


def downgrade() -> None:
    for code, gb in RECORDING_QUOTAS:
        feature = f"{gb} GB de grabaciones en la nube"
        op.execute(
            f"UPDATE plans SET features = features - '{feature}' WHERE code = '{code}'"
        )
    op.drop_column("plans", "max_recording_gb")
    op.drop_column("devices", "recording_on")
