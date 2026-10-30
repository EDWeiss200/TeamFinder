"""Модели мероприятий (Event) и регистраций участников (EventRegistration)."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Enum as SQLEnum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from database.database import Base
from models.enums import EventFormat, EventStatus


class Event(Base):
    """Мероприятие (хакатон, кейс-чемпионат)."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str] = mapped_column(String(500), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, nullable=False)
    organizer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organizer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[EventStatus] = mapped_column(
        SQLEnum(EventStatus, name="event_status_enum", native_enum=False),
        default=EventStatus.REGISTRATION,
        nullable=False,
    )
    format: Mapped[EventFormat] = mapped_column(
        SQLEnum(EventFormat, name="event_format_enum", native_enum=False),
        nullable=False,
    )

    tags: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default="{}",
        nullable=False,
    )
    banner_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    theme_color: Mapped[str] = mapped_column(
        String(7),
        default="#0044FF",
        server_default="#0044FF",
        nullable=False,
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    invite_code: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False,
    )

    min_team_size: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    max_team_size: Mapped[int] = mapped_column(SmallInteger, default=5, nullable=False)

    registration_start: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    registration_end: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    event_start: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    submission_deadline: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    event_end: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )

    custom_fields_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Связи
    registrations = relationship(
        "EventRegistration",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    teams = relationship(
        "Team",
        back_populates="event",
        cascade="all, delete-orphan",
    )


class EventRegistration(Base):
    """Регистрация пользователя на мероприятие (участник или одиночка)."""

    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_event_user"),
    )

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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role_in_team: Mapped[str] = mapped_column(String(100), nullable=False)
    custom_answers: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    joined_team_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    registered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Связи
    event = relationship("Event", back_populates="registrations")
    team = relationship("Team", back_populates="members")
    user = relationship("User")
