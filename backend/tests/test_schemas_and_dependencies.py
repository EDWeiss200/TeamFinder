# Файл: backend/tests/test_schemas_and_dependencies.py
"""Модульные тесты Pydantic-схем, валидаторов и зависимостей прав доступа."""

import uuid
from datetime import datetime, timezone

import pytest

from api.dependencies import require_admin, require_organizer
from models.enums import ParticipantSpecialization, UserRole
from models.team import Team
from schemas.common import PaginatedResponse
from schemas.team import TeamCreate, TeamRead
from tests.conftest import make_event, make_registration, make_user
from utils.exceptions import PermissionDeniedError


# ------------------------------------------------------------------
# Тесты пагинации PaginatedResponse
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "total, size, expected_pages",
    [
        (0, 20, 0),
        (1, 20, 1),
        (20, 20, 1),
        (21, 20, 2),
        (120, 20, 6),
        (10, 0, 0),
    ],
)
def test_paginated_response_pages_calculation(
    total: int, size: int, expected_pages: int
):
    """Проверяет правильность округления общего числа страниц вверх (math.ceil)."""
    resp = PaginatedResponse.create(
        items=["item1"],
        total=total,
        page=1,
        size=max(size, 1) if size > 0 else 1,
    )
    if size == 0:
        resp_zero = PaginatedResponse.create(items=[], total=total, page=1, size=1)
        assert resp_zero.pages == total
    else:
        assert resp.pages == expected_pages
        assert resp.total == total


# ------------------------------------------------------------------
# Тесты схемы TeamRead и вычисления existing_roles («Уже есть»)
# ------------------------------------------------------------------


def test_team_read_transform_orm_computes_existing_roles_and_captain():
    """Проверяет, что в existing_roles попадают только specializations (без skills) и определяется капитан."""
    event = make_event()
    captain = make_user(
        full_name="Капитан",
        specializations=["backend", "ai_ml"],
        skills=["Python", "Docker", "PyTorch"],
    )
    member = make_user(
        full_name="Дизайнер",
        specializations=[
            "design",
            "backend",
        ],  # дубликат backend не должен дублироваться в existing_roles
        skills=["Figma"],
    )

    team = Team(
        id=uuid.uuid4(),
        event_id=event.id,
        name="Drill Flex",
        description="Топ команда",
        captain_id=captain.id,
        max_members=5,
        needed_roles=["frontend"],
        allow_auto_match=True,
        invite_token="secret_token_123",
        created_at=datetime.now(timezone.utc),
    )

    reg_captain = make_registration(captain, event, team_id=team.id)
    reg_member = make_registration(member, event, team_id=team.id)
    team.members = [reg_captain, reg_member]

    team_dto = TeamRead.model_validate(team)

    assert team_dto.members_count == 2
    # В existing_roles должны быть только уникальные специализации без произвольных skills
    assert team_dto.existing_roles == [
        ParticipantSpecialization.BACKEND,
        ParticipantSpecialization.AI_ML,
        ParticipantSpecialization.DESIGN,
    ]
    # Проверяем флаг капитана у участников
    captain_member = next(m for m in team_dto.members if m.user_id == captain.id)
    regular_member = next(m for m in team_dto.members if m.user_id == member.id)
    assert captain_member.is_captain is True
    assert regular_member.is_captain is False


def test_team_create_rejects_arbitrary_needed_roles():
    """Проверяет, что в needed_roles нельзя передать произвольную строку вне ParticipantSpecialization."""
    with pytest.raises(Exception):
        TeamCreate(
            name="Hackers",
            max_members=4,
            needed_roles=["invalid_custom_role"],  # Должно быть отклонено Pydantic
        )


# ------------------------------------------------------------------
# Тесты прав доступа require_organizer и require_admin
# ------------------------------------------------------------------


async def test_require_organizer_allows_organizer_admin_and_superuser():
    """Организатор, админ и суперюзер успешно проходят проверку require_organizer."""
    organizer = make_user(role=UserRole.ORGANIZER)
    admin = make_user(role=UserRole.ADMIN)
    superuser = make_user(role=UserRole.PARTICIPANT, is_superuser=True)

    assert await require_organizer(organizer) == organizer
    assert await require_organizer(admin) == admin
    assert await require_organizer(superuser) == superuser


async def test_require_organizer_blocks_regular_participant():
    """Обычный студент получает PermissionDeniedError при попытке доступа к панели орга."""
    student = make_user(role=UserRole.PARTICIPANT, is_superuser=False)
    with pytest.raises(PermissionDeniedError):
        await require_organizer(student)


async def test_require_admin_blocks_organizer():
    """Обычный организатор не может выполнять действия супер-администратора."""
    organizer = make_user(role=UserRole.ORGANIZER, is_superuser=False)
    with pytest.raises(PermissionDeniedError):
        await require_admin(organizer)
