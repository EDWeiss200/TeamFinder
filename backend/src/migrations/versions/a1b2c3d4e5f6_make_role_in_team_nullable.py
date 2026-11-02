"""Удаление избыточной колонки role_in_team из таблицы event_registrations.

Revision ID: a1b2c3d4e5f6
Revises: f856f6606b48
Create Date: 2026-11-02 11:24:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f856f6606b48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Удаление избыточной колонки role_in_team."""
    op.drop_column("event_registrations", "role_in_team")


def downgrade() -> None:
    """Восстановление колонки role_in_team при откате."""
    op.add_column(
        "event_registrations",
        sa.Column("role_in_team", sa.String(length=100), nullable=True),
    )
