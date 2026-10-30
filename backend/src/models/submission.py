"""Модель сданных решений (Submission)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from database.database import Base


class Submission(Base):
    """Сданный проект команды на хакатоне."""

    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    github_url: Mapped[str] = mapped_column(String(512), nullable=False)
    presentation_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    demo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Связи
    team = relationship("Team", back_populates="submission")
    submitted_by_user = relationship("User", foreign_keys=[submitted_by_user_id])
