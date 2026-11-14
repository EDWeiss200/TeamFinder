"""Pydantic DTO схемы приложения."""

from schemas.common import PaginatedResponse
from schemas.event import (
    EventCreate,
    EventDetailRead,
    EventRead,
    EventRegistrationCreate,
    EventRegistrationRead,
    EventUpdate,
    SoloParticipantRead,
    UserEventItemRead,
)
from schemas.team import (
    TeamApplicationCreate,
    TeamCreate,
    TeamDetailRead,
    TeamMemberRead,
    TeamRead,
    TeamInviteCreate,
    TeamRequestRead,
    TeamUpdate,
)
from schemas.upload import ImageUploadResponse

__all__ = [
    "PaginatedResponse",
    "ImageUploadResponse",
    "EventCreate",
    "EventUpdate",
    "EventRead",
    "EventDetailRead",
    "EventRegistrationCreate",
    "EventRegistrationRead",
    "SoloParticipantRead",
    "UserEventItemRead",
    "TeamCreate",
    "TeamUpdate",
    "TeamRead",
    "TeamDetailRead",
    "TeamMemberRead",
    "TeamApplicationCreate",
    "TeamInviteCreate",
    "TeamRequestRead",
]
