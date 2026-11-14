# Файл: backend/tests/conftest.py
"""Глобальные фикстуры, FakeUnitOfWork и фабрики тестовых данных."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from models.enums import (
    EventFormat,
    EventStatus,
    ParticipantSpecialization,
    UserRole,
)
from models.event import Event, EventRegistration
from models.team import Team
from models.user import User
from utils.uow import IUnitOfWork


class FakeUnitOfWork(IUnitOfWork):
    """Тестовый двойник UnitOfWork с замоканными репозиториями."""

    def __init__(self) -> None:
        self.users = AsyncMock()
        self.events = AsyncMock()
        self.registrations = AsyncMock()
        self.teams = AsyncMock()
        self.requests = AsyncMock()
        self.submissions = AsyncMock()
        self.teams.find_one_or_none.return_value = None
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            await self.rollback()
        self.closed = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture
def fake_uow() -> FakeUnitOfWork:
    """Фикстура чистого FakeUnitOfWork для каждого теста."""
    return FakeUnitOfWork()


# ------------------------------------------------------------------
# Фабрики тестовых сущностей
# ------------------------------------------------------------------


def make_user(**overrides: Any) -> User:
    """Создает объект User в памяти со стандартными полями."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid.uuid4(),
        "email": "student@sfu-kras.ru",
        "hashed_password": "hashed_secret_password",
        "is_active": True,
        "is_superuser": False,
        "is_verified": False,
        "role": UserRole.PARTICIPANT,
        "full_name": "Григорий Мухоедов",
        "nickname": "grisha_dev",
        "avatar_url": None,
        "university": "СФУ ИКИТ",
        "study_group": "КИ25-20Б",
        "course": 2,
        "bio": "Backend developer",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "specializations": [ParticipantSpecialization.BACKEND.value],
        "vk_url": "https://vk.com/test",
        "github_url": "https://github.com/test",
        "telegram_id": None,
        "telegram_username": "grisha_tg",
        "telegram_bind_token": None,
        "telegram_bind_token_expires_at": None,
        "is_bot_active": False,
        "created_at": now,
    }
    defaults.update(overrides)
    return User(**defaults)


def make_event(**overrides: Any) -> Event:
    """Создает объект Event в памяти с актуальными дедлайнами в будущем."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid.uuid4(),
        "title": "О! Хакатон 2026",
        "short_description": "Всероссийский хакатон",
        "description_md": "# Описание кейса",
        "organizer_name": "СФУ",
        "organizer_id": uuid.uuid4(),
        "status": EventStatus.REGISTRATION,
        "format": EventFormat.HYBRID,
        "tags": ["Хакатон", "Веб-разработка"],
        "banner_url": None,
        "theme_color": "#0044FF",
        "is_public": True,
        "is_featured": True,
        "invite_code": "sfu_hack_2026",
        "min_team_size": 3,
        "max_team_size": 5,
        "registration_start": now - timedelta(days=2),
        "registration_end": now + timedelta(days=5),
        "event_start": now + timedelta(days=6),
        "submission_deadline": now + timedelta(days=8),
        "event_end": now + timedelta(days=9),
        "custom_fields_schema": None,
        "created_at": now,
    }
    defaults.update(overrides)
    return Event(**defaults)


def make_registration(user: User, event: Event, **overrides: Any) -> EventRegistration:
    """Создает объект регистрации участника на мероприятие."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid.uuid4(),
        "event_id": event.id,
        "user_id": user.id,
        "team_id": None,
        "custom_answers": None,
        "joined_team_at": None,
        "registered_at": now,
    }
    defaults.update(overrides)
    reg = EventRegistration(**defaults)
    reg.user = user
    reg.event = event
    return reg


def make_team(event: Event, captain: User, **overrides: Any) -> Team:
    """Создает объект Team в памяти с капитаном и базовыми полями."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid.uuid4(),
        "event_id": event.id,
        "name": "Drill Flex",
        "description": "Разрабатываем платформу для подбора команд",
        "captain_id": captain.id,
        "max_members": event.max_team_size,
        "needed_roles": [ParticipantSpecialization.DESIGN.value],
        "allow_auto_match": True,
        "invite_token": "secret-invite-token",
        "created_at": now,
    }
    defaults.update(overrides)
    team = Team(**defaults)
    team.event = event
    team.captain = captain
    team.members = []
    return team


@pytest.fixture
async def async_client() -> AsyncClient:
    """Асинхронный HTTP-клиент для тестирования роутеров FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    # Очищаем переопределения зависимостей после каждого теста
    app.dependency_overrides.clear()
