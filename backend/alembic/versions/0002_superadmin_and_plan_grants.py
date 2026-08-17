"""Rol de super-admin, origen/vencimiento del plan y auditoría de asignaciones.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-17

Se aplica sobre una base con datos reales: las columnas nuevas de `users` son
NOT NULL con server_default, de modo que las filas existentes se rellenan solas
(los usuarios ya creados quedan como 'signup', sin vencimiento y sin permisos).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("plan_source", sa.Text(), nullable=False, server_default="signup"),
    )
    op.add_column(
        "users",
        sa.Column("plan_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "plan_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        # NULL = otorgado automáticamente (webhook de una pasarela de pago).
        sa.Column("granted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_plan_grants_user_id", "plan_grants", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_grants_user_id", table_name="plan_grants")
    op.drop_table("plan_grants")
    op.drop_column("users", "plan_expires_at")
    op.drop_column("users", "plan_source")
    op.drop_column("users", "is_superadmin")
