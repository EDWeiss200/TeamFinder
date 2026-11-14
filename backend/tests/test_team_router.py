# Файл: backend/tests/test_team_router.py
"""API-тесты роутера команд."""

import uuid
from unittest.mock import AsyncMock

from httpx import AsyncClient

from api.dependencies import team_service
from api.team_router import current_user_or_none
from auth.auth import current_user
from main import app
from schemas.common import PaginatedResponse
from tests.conftest import make_event, make_team, make_user


def make_team_detail_payload(team_id: uuid.UUID | None = None) -> dict:
    """Собрать минимальный payload, совместимый с TeamDetailRead."""
    user = make_user()
    event = make_event()
    team = make_team(event, user, id=team_id or uuid.uuid4())
    return {
        "id": team.id,
        "event_id": event.id,
        "name": team.name,
        "description": team.description,
        "captain_id": user.id,
        "max_members": team.max_members,
        "needed_roles": [],
        "existing_roles": [],
        "members_count": 1,
        "members": [
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "nickname": user.nickname,
                "avatar_url": user.avatar_url,
                "is_captain": True,
                "specializations": user.specializations,
                "skills": user.skills,
                "telegram_username": user.telegram_username,
                "joined_team_at": None,
            }
        ],
        "allow_auto_match": True,
        "created_at": team.created_at.isoformat(),
        "invite_token": "secret-token",
        "is_user_member": True,
        "is_user_captain": True,
    }


async def test_get_event_teams_endpoint_returns_paginated_catalog(
    async_client: AsyncClient,
):
    """GET /events/{event_id}/teams возвращает PaginatedResponse и прокидывает фильтры."""
    event = make_event()
    captain = make_user()
    team = make_team(event, captain)

    mock_service = AsyncMock()
    mock_service.get_event_teams.return_value = PaginatedResponse.create(
        items=[team],
        total=1,
        page=1,
        size=20,
    )
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.get(
        f"/api/v1/events/{event.id}/teams",
        params={"needed_role": "backend", "has_free_slots": "true"},
    )

    assert response.status_code == 200
    called_kwargs = mock_service.get_event_teams.call_args.kwargs
    assert called_kwargs["event_id"] == event.id
    assert called_kwargs["needed_role"].value == "backend"
    assert called_kwargs["has_free_slots"] is True


async def test_create_team_endpoint_returns_team_detail(async_client: AsyncClient):
    """POST /events/{event_id}/teams создает команду и возвращает TeamDetailRead."""
    user = make_user()
    event = make_event()
    team_id = uuid.uuid4()

    mock_service = AsyncMock()
    mock_service.create_team.return_value = type("TeamStub", (), {"id": team_id})()
    mock_service.get_team_detail.return_value = make_team_detail_payload(
        team_id=team_id
    )

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.post(
        f"/api/v1/events/{event.id}/teams",
        json={
            "name": "Drill Flex",
            "description": "desc",
            "max_members": 5,
            "needed_roles": ["backend"],
            "allow_auto_match": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(team_id)


async def test_get_team_detail_endpoint_masks_token_for_anonymous(
    async_client: AsyncClient,
):
    """GET /teams/{team_id} работает с optional auth и отдает маскированный invite_token."""
    team_id = uuid.uuid4()
    payload = make_team_detail_payload(team_id=team_id)
    payload["invite_token"] = None
    payload["is_user_member"] = False
    payload["is_user_captain"] = False

    mock_service = AsyncMock()
    mock_service.get_team_detail.return_value = payload

    app.dependency_overrides[current_user_or_none] = lambda: None
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.get(f"/api/v1/teams/{team_id}")

    assert response.status_code == 200
    assert response.json()["invite_token"] is None


async def test_update_team_endpoint_returns_updated_detail(async_client: AsyncClient):
    """PATCH /teams/{team_id} обновляет команду и возвращает её detail."""
    user = make_user()
    team_id = uuid.uuid4()
    payload = make_team_detail_payload(team_id=team_id)
    payload["name"] = "Updated Team"

    mock_service = AsyncMock()
    mock_service.update_team.return_value = object()
    mock_service.get_team_detail.return_value = payload

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.patch(
        f"/api/v1/teams/{team_id}",
        json={"name": "Updated Team"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Team"


async def test_regenerate_token_endpoint_returns_new_token(async_client: AsyncClient):
    """POST /teams/{team_id}/regenerate-token возвращает новый invite_token."""
    user = make_user()
    team_id = uuid.uuid4()

    mock_service = AsyncMock()
    mock_service.regenerate_invite_token.return_value = "brand-new-token"

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.post(f"/api/v1/teams/{team_id}/regenerate-token")

    assert response.status_code == 200
    assert response.json() == {"invite_token": "brand-new-token"}


async def test_join_by_token_endpoint_returns_team_detail(async_client: AsyncClient):
    """POST /teams/join-by-token/{invite_token} вступает в команду и возвращает detail."""
    user = make_user()
    team_id = uuid.uuid4()

    mock_service = AsyncMock()
    mock_service.join_by_invite_token.return_value = type(
        "TeamStub", (), {"id": team_id}
    )()
    mock_service.get_team_detail.return_value = make_team_detail_payload(
        team_id=team_id
    )

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.post("/api/v1/teams/join-by-token/token-123")

    assert response.status_code == 200
    assert response.json()["id"] == str(team_id)


async def test_leave_team_endpoint_returns_null_when_team_deleted(
    async_client: AsyncClient,
):
    """POST /teams/{team_id}/leave возвращает null, если команда удалена после выхода."""
    user = make_user()
    team_id = uuid.uuid4()

    mock_service = AsyncMock()
    mock_service.leave_team.return_value = None

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.post(f"/api/v1/teams/{team_id}/leave")

    assert response.status_code == 200
    assert response.text == "null"


async def test_kick_member_endpoint_returns_team_detail(async_client: AsyncClient):
    """DELETE /teams/{team_id}/members/{user_id} возвращает актуальный состав команды."""
    actor = make_user()
    target_user = make_user()
    team_id = uuid.uuid4()

    mock_service = AsyncMock()
    mock_service.kick_member.return_value = type("TeamStub", (), {"id": team_id})()
    mock_service.get_team_detail.return_value = make_team_detail_payload(
        team_id=team_id
    )

    app.dependency_overrides[current_user] = lambda: actor
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.delete(
        f"/api/v1/teams/{team_id}/members/{target_user.id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(team_id)
