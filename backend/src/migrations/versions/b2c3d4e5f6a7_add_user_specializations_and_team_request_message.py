"""Добавление specializations в users и message в team_requests.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-02 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Идентификаторы ревизии, используемые Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Обновление схемы базы данных."""
    # Таблица users: добавление массива specializations и удаление устаревшего primary_role
    op.add_column(
        "users",
        sa.Column(
            "specializations",
            postgresql.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.drop_column("users", "primary_role")

    # Таблица team_requests: target_role становится nullable, добавляется поле message
    op.alter_column(
        "team_requests",
        "target_role",
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.add_column(
        "team_requests",
        sa.Column("message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Откат изменений схемы базы данных."""
    # Таблица team_requests: удаление message и возврат target_role в NOT NULL
    op.drop_column("team_requests", "message")
    op.alter_column(
        "team_requests",
        "target_role",
        existing_type=sa.String(length=100),
        nullable=False,
    )

    # Таблица users: возврат primary_role и удаление specializations
    op.add_column(
        "users",
        sa.Column("primary_role", sa.String(length=100), nullable=True),
    )
    op.drop_column("users", "specializations")
