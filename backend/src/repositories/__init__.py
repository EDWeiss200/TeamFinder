"""Экспорт классов репозиториев приложения."""

from repositories.event_repo import EventRepository
from repositories.registration_repo import EventRegistrationRepository
from repositories.user_repo import UserRepository

__all__ = [
    "UserRepository",
    "EventRepository",
    "EventRegistrationRepository",
]
