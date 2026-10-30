"""Модели команд (Team) и заявок/приглашений (TeamRequest)."""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Enum as SQLEnum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from database.database import Base
from models.enums import TeamRequestStatus, TeamRequestType


class Team(Base):
    """Команда внутри конкретного мероприятия."""

    __tablename__ = "teams"

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
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    max_members: Mapped[int] = mapped_column(SmallInteger, default=5, nullable=False)
    needed_roles: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default="{}",
        nullable=False,
    )
    allow_auto_match: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    invite_token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Связи
    event = relationship("Event", back_populates="teams")
    captain = relationship("User", foreign_keys=[captain_id])
    members = relationship(
        "EventRegistration",
        back_populates="team",
    )
    requests = relationship(
        "TeamRequest",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    submission = relationship(
        "Submission",
        back_populates="team",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TeamRequest(Base):
    """Заявка участника в команду или приглашение от капитана."""

    __tablename__ = "team_requests"

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
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_role: Mapped[str] = mapped_column(String(100), nullable=False)

    request_type: Mapped[TeamRequestType] = mapped_column(
        SQLEnum(TeamRequestType, name="team_request_type_enum", native_enum=False),
        nullable=False,
    )
    status: Mapped[TeamRequestStatus] = mapped_column(
        SQLEnum(TeamRequestStatus, name="team_request_status_enum", native_enum=False),
        default=TeamRequestStatus.PENDING_CAPTAIN,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Связи
    team = relationship("Team", back_populates="requests")
    user = relationship("User", foreign_keys=[user_id])
