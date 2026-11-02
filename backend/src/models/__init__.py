"""Экспорт всех моделей и перечислений для приложения и Alembic."""

from database.database import Base
from models.enums import (
    EventFormat,
    EventStatus,
    ParticipantSpecialization,
    TeamRequestStatus,
    TeamRequestType,
    UserRole,
)
from models.event import Event, EventRegistration
from models.submission import Submission
from models.team import Team, TeamRequest
from models.user import User

__all__ = [
    "Base",
    "User",
    "Event",
    "EventRegistration",
    "Team",
    "TeamRequest",
    "Submission",
    "UserRole",
    "ParticipantSpecialization",
    "EventStatus",
    "EventFormat",
    "TeamRequestStatus",
    "TeamRequestType",
]
