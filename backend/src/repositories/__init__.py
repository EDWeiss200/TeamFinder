"""Репозитории для работы с сущностями базы данных."""

from repositories.event_repo import EventRepository
from repositories.registration_repo import EventRegistrationRepository
from repositories.request_repo import RequestRepository
from repositories.submission_repo import SubmissionRepository
from repositories.team_repo import TeamRepository
from repositories.user_repo import UserRepository

__all__ = [
    "UserRepository",
    "EventRepository",
    "EventRegistrationRepository",
    "TeamRepository",
    "RequestRepository",
    "SubmissionRepository",
]
