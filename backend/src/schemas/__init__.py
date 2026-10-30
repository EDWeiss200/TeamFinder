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
]
