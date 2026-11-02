"""Экспорт Pydantic-схем приложения."""

from schemas.event import (
    EventBase,
    EventCreate,
    EventDetailRead,
    EventRead,
    EventRegistrationCreate,
    EventRegistrationRead,
    EventRegistrationUserRead,
    EventUpdate,
    SoloParticipantRead,
    UserEventItemRead,
)
from schemas.team import (
    TeamBase,
    TeamCreate,
    TeamDetailRead,
    TeamMemberRead,
    TeamRead,
    TeamUpdate,
)

__all__ = [
    "EventBase",
    "EventCreate",
    "EventUpdate",
    "EventRead",
    "EventDetailRead",
    "EventRegistrationCreate",
    "EventRegistrationRead",
    "EventRegistrationUserRead",
    "SoloParticipantRead",
    "UserEventItemRead",
    "TeamBase",
    "TeamCreate",
    "TeamUpdate",
    "TeamRead",
    "TeamDetailRead",
    "TeamMemberRead",
]
