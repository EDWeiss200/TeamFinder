"""Добавление telegram_bind_token_expires_at в users и индекса uq_active_team_user_request в team_requests.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-09 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Идентификаторы ревизии, используемые Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Обновление схемы базы данных."""
    # Таблица users: добавление срока жизни токена привязки Telegram
    op.add_column(
        "users",
        sa.Column(
            "telegram_bind_token_expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # Таблица team_requests: частичный уникальный индекс для защиты от встречных заявок
    op.create_index(
        "uq_active_team_user_request",
        "team_requests",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_captain', 'pending_user')"),
    )


def downgrade() -> None:
    """Откат изменений схемы базы данных."""
    # Таблица team_requests: удаление индекса
    op.drop_index("uq_active_team_user_request", table_name="team_requests")

    # Таблица users: удаление колонки telegram_bind_token_expires_at
    op.drop_column("users", "telegram_bind_token_expires_at")
