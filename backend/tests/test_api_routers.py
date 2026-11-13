# Файл: backend/tests/test_api_routers.py
"""Модульные тесты API-роутеров, безопасности схем и глобальных обработчиков ошибок."""

import uuid
from unittest.mock import AsyncMock

from httpx import AsyncClient

from api.dependencies import event_service, user_service
from auth.auth import current_user
from main import app
from schemas.common import PaginatedResponse
from tests.conftest import make_event, make_registration, make_user
from utils.exceptions import (
    AlreadyInTeamError,
    EntityNotFoundError,
    PermissionDeniedError,
    TeamIsFullError,
)


async def test_health_check_endpoint(async_client: AsyncClient):
    """Эндпоинт /health возвращает статус 200 OK."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_get_user_by_id_hides_private_fields(async_client: AsyncClient):
    """SECURITY-ТЕСТ: GET /api/v1/users/{id} НЕ должен возвращать email, telegram_id и is_superuser."""
    caller = make_user()
    target_user = make_user(
        email="secret_private@mail.ru",
        telegram_id=777888999,
        is_superuser=True,
    )

    mock_user_service = AsyncMock()
    mock_user_service.get_user_by_id.return_value = target_user

    app.dependency_overrides[current_user] = lambda: caller
    app.dependency_overrides[user_service] = lambda: mock_user_service

    response = await async_client.get(f"/api/v1/users/{target_user.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == target_user.full_name
    assert "email" not in data
    assert "telegram_id" not in data
    assert "hashed_password" not in data
    assert "is_superuser" not in data


async def test_get_me_returns_full_private_profile(async_client: AsyncClient):
    """GET /api/v1/users/me возвращает полный профиль владельца, включая email и telegram_id."""
    me = make_user(email="my_own@mail.ru", telegram_id=111222333)
    mock_user_service = AsyncMock()
    mock_user_service.get_user_by_id.return_value = me

    app.dependency_overrides[current_user] = lambda: me
    app.dependency_overrides[user_service] = lambda: mock_user_service

    response = await async_client.get("/api/v1/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "my_own@mail.ru"
    assert data["telegram_id"] == 111222333


async def test_solo_participants_merges_specialization_skills_and_tags(async_client: AsyncClient):
    """Проверяет, что роутер /solo-participants объединяет параметры specialization, skills и tags."""
    me = make_user()
    event = make_event()
    reg = make_registration(me, event)

    mock_event_service = AsyncMock()
    mock_event_service.get_solo_participants.return_value = PaginatedResponse.create(
        items=[reg], total=1, page=1, size=20
    )

    app.dependency_overrides[current_user] = lambda: me
    app.dependency_overrides[event_service] = lambda: mock_event_service

    response = await async_client.get(
        f"/api/v1/events/{event.id}/solo-participants",
        params={"specialization": "backend", "skills": ["Docker", "FastAPI"]},
    )

    assert response.status_code == 200
    called_kwargs = mock_event_service.get_solo_participants.call_args.kwargs
    assert set(called_kwargs["tags"]) == {"backend", "Docker", "FastAPI"}


async def test_domain_exceptions_map_to_proper_http_status_codes(async_client: AsyncClient):
    """Проверяет, что exception_handlers.py возвращает 404, 403 и 409 для доменных исключений."""
    me = make_user()
    app.dependency_overrides[current_user] = lambda: me

    mock_service = AsyncMock()
    app.dependency_overrides[user_service] = lambda: mock_service

    # 1. EntityNotFoundError -> 404 Not Found
    mock_service.get_user_by_id.side_effect = EntityNotFoundError("Не найдено")
    res_404 = await async_client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert res_404.status_code == 404

    # 2. PermissionDeniedError -> 403 Forbidden
    mock_service.get_user_by_id.side_effect = PermissionDeniedError("Нет прав")
    res_403 = await async_client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert res_403.status_code == 403

    # 3. TeamIsFullError & AlreadyInTeamError -> 409 Conflict
    mock_service.get_user_by_id.side_effect = TeamIsFullError("Мест нет")
    res_409_full = await async_client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert res_409_full.status_code == 409

    mock_service.get_user_by_id.side_effect = AlreadyInTeamError("Уже в команде")
    res_409_in_team = await async_client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert res_409_in_team.status_code == 409