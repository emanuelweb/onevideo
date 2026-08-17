"""Esquema inicial y seed de los 4 planes.

Revision ID: 0001
Revises:
Create Date: 2026-08-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price_usd_month", sa.Numeric(6, 2), nullable=False),
        sa.Column("max_devices", sa.Integer(), nullable=False),
        sa.Column("max_resolution", sa.Text(), nullable=False),
        sa.Column("max_fps", sa.Integer(), nullable=False),
        sa.Column("monthly_hours", sa.Integer(), nullable=True),
        sa.Column("features", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("code", name="uq_plans_code"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ux_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("device_token_hash", sa.Text(), nullable=True),
        sa.Column("view_token", sa.Text(), nullable=False),
        sa.Column("camera_on", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.Text(), nullable=False, server_default="offline"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])

    op.create_table(
        "pairing_codes",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pairing_codes_device_id", "pairing_codes", ["device_id"])

    op.create_table(
        "stream_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_stream_sessions_device_id", "stream_sessions", ["device_id"])
    op.create_index("ix_stream_sessions_ended_at", "stream_sessions", ["ended_at"])

    # Seed de los 4 planes. SQL explícito con casts ::jsonb para que funcione
    # tanto en modo online como en modo offline (--sql).
    seed_rows = [
        (
            "free",
            "Gratis",
            "0.00",
            1,
            "720p",
            30,
            "15",
            '["1 dispositivo", "720p a 30 fps", "15 horas por mes", '
            '"Control remoto desde el dashboard"]',
            1,
        ),
        (
            "creator",
            "Creador",
            "4.99",
            1,
            "1080p",
            30,
            "60",
            '["1 dispositivo", "1080p a 30 fps", "60 horas por mes", '
            '"Control remoto desde el dashboard"]',
            2,
        ),
        (
            "pro",
            "Pro",
            "9.99",
            2,
            "1080p",
            60,
            "150",
            '["2 dispositivos", "1080p a 60 fps", "150 horas por mes", '
            '"Control remoto desde el dashboard", "Soporte prioritario"]',
            3,
        ),
        (
            "studio",
            "Estudio",
            "19.99",
            4,
            "1080p",
            60,
            "NULL",
            '["4 dispositivos", "1080p a 60 fps", "Horas ilimitadas (uso justo)", '
            '"Control remoto desde el dashboard", "Soporte prioritario"]',
            4,
        ),
    ]
    values_sql = ",\n".join(
        f"('{code}', '{name}', {price}, {max_devices}, '{max_resolution}', "
        f"{max_fps}, {monthly_hours}, '{features}'::jsonb, {sort_order})"
        for code, name, price, max_devices, max_resolution, max_fps, monthly_hours, features, sort_order in seed_rows
    )
    op.execute(
        "INSERT INTO plans (code, name, price_usd_month, max_devices, max_resolution, "
        f"max_fps, monthly_hours, features, sort_order) VALUES\n{values_sql}"
    )


def downgrade() -> None:
    op.drop_index("ix_stream_sessions_ended_at", table_name="stream_sessions")
    op.drop_index("ix_stream_sessions_device_id", table_name="stream_sessions")
    op.drop_table("stream_sessions")
    op.drop_index("ix_pairing_codes_device_id", table_name="pairing_codes")
    op.drop_table("pairing_codes")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_table("devices")
    op.drop_index("ux_users_email_lower", table_name="users")
    op.drop_table("users")
    op.drop_table("plans")
