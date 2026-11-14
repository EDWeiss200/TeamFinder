# Файл: backend/tests/test_request_adversarial.py
"""Каверзные (adversarial) тесты для Фазы 5: пайплайн заявок, anti-collision, овербукинг и rate-limiting."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from api.dependencies import team_service
from auth.auth import current_user
from main import app
from models.enums import (
    EventStatus,
    ParticipantSpecialization,
    TeamRequestStatus,
    TeamRequestType,
)
from schemas.team import TeamApplicationCreate, TeamInviteCreate
from services.team_services import TeamServices
from tests.conftest import (
    FakeUnitOfWork,
    make_event,
    make_registration,
    make_team,
    make_team_request,
    make_user,
)
from utils.exceptions import (
    InvalidStateError,
    PermissionDeniedError,
    TeamIsFullError,
)


# ------------------------------------------------------------------
# 1. Одобрение заявки участника, не зарегистрированного на хакатон
# ------------------------------------------------------------------


async def test_adv_req_captain_cannot_approve_unregistered_candidate(
    fake_uow: FakeUnitOfWork,
):
    """Капитан не может одобрить заявку (captain_approve_request), если у кандидата нет регистрации на ивент."""
    event = make_event()
    captain = make_user()
    ghost_user = make_user()
    team = make_team(event, captain)
    req = make_team_request(
        event,
        team,
        ghost_user,
        status=TeamRequestStatus.PENDING_CAPTAIN,
        request_type=TeamRequestType.APPLICATION,
    )

    fake_uow.requests.get_by_id_for_update.return_value = req
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    # Кандидат НЕ зарегистрирован на мероприятие (None)
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = None
    fake_uow.teams.get_members_count.return_value = 1

    service = TeamServices(fake_uow)

    with pytest.raises(InvalidStateError):
        await service.captain_approve_request(request_id=req.id, captain_id=captain.id)


# ------------------------------------------------------------------
# 2. Сохранение target_role и message при встречном отклике (Anti-Collision)
# ------------------------------------------------------------------


async def test_adv_req_anti_collision_apply_persists_target_role_and_message(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 2.4 & 6.4: если висел инвайт без роли (PENDING_USER), а студент подает встречный
    отклик с target_role и message, эти поля обязаны сохраниться в БД при переходе в ACCEPTED."""
    event = make_event(max_team_size=4)
    captain = make_user()
    student = make_user(specializations=["design", "frontend"])
    team = make_team(event, captain, max_members=4, needed_roles=["design", "frontend"])
    reg = make_registration(student, event)

    existing_invite = make_team_request(
        event,
        team,
        student,
        target_role=None,
        message=None,
        request_type=TeamRequestType.INVITE,
        status=TeamRequestStatus.PENDING_USER,
    )

    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.users.find_one_or_none.return_value = student
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = reg
    fake_uow.teams.get_members_count.return_value = 1
    fake_uow.requests.get_active_request.return_value = existing_invite
    fake_uow.requests.get_by_id_with_relations.return_value = existing_invite

    service = TeamServices(fake_uow)
    await service.apply_to_team(
        team_id=team.id,
        user_id=student.id,
        data=TeamApplicationCreate(
            target_role=ParticipantSpecialization.FRONTEND,
            message="Закрою фронтенд!",
        ),
    )

    # Проверяем, что в БД (requests.update) ушли не только status, но и target_role/message
    update_call_payload = fake_uow.requests.update.call_args[0][1]
    assert update_call_payload.get("status") == TeamRequestStatus.ACCEPTED
    assert update_call_payload.get("target_role") == "frontend", (
        f"При anti-collision в БД потерялся target_role! Передано в update: {update_call_payload}"
    )
    assert update_call_payload.get("message") == "Закрою фронтенд!"


# ------------------------------------------------------------------
# 3. Ленивый дедлайн во время подтверждения заявки (user_confirm_request)
# ------------------------------------------------------------------


async def test_adv_req_lazy_deadline_blocks_user_confirm_and_cancels_requests(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 5.2: если registration_end истек за секунду до нажатия 'Подтвердить вступление',
    событие лениво переходит в TEAM_LOCK, все заявки отменяются, а вступление блокируется."""
    past = datetime.now(timezone.utc) - timedelta(seconds=30)
    event = make_event(status=EventStatus.REGISTRATION, registration_end=past)
    captain = make_user()
    student = make_user()
    team = make_team(event, captain)
    req = make_team_request(
        event,
        team,
        student,
        status=TeamRequestStatus.PENDING_USER,
        request_type=TeamRequestType.INVITE,
    )

    fake_uow.requests.get_by_id_for_update.return_value = req
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)

    with pytest.raises(InvalidStateError):
        await service.user_confirm_request(request_id=req.id, user_id=student.id)

    assert event.status == EventStatus.TEAM_LOCK
    fake_uow.requests.cancel_all_event_pending_requests.assert_awaited_once_with(event.id)


# ------------------------------------------------------------------
# 4. Запрет повторного отклонения уже завершенной заявки (ACCEPTED / REJECTED / CANCELLED)
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "terminal_status",
    [
        TeamRequestStatus.ACCEPTED,
        TeamRequestStatus.REJECTED,
        TeamRequestStatus.CANCELLED,
    ],
)
async def test_adv_req_cannot_reject_already_resolved_request(
    fake_uow: FakeUnitOfWork,
    terminal_status: TeamRequestStatus,
):
    """SPEC 6.4: нельзя вызвать /reject для заявки, которая уже принята, отклонена или отменена."""
    event = make_event()
    captain = make_user()
    student = make_user()
    team = make_team(event, captain)
    req = make_team_request(event, team, student, status=terminal_status)

    fake_uow.requests.get_by_id_for_update.return_value = req
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)

    with pytest.raises(InvalidStateError):
        await service.reject_request(request_id=req.id, actor_user_id=captain.id)


# ------------------------------------------------------------------
# 5. Обычный участник команды (не капитан) не может инвайтить или одобрять
# ------------------------------------------------------------------


async def test_adv_req_regular_team_member_cannot_invite_or_approve(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 2.4 & 6.4: обычный член команды (не капитан) получает PermissionDeniedError при инвайте или апруве."""
    event = make_event()
    captain = make_user()
    regular_member = make_user()
    solo_student = make_user()
    team = make_team(event, captain)
    req = make_team_request(
        event, team, solo_student, status=TeamRequestStatus.PENDING_CAPTAIN
    )

    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.requests.get_by_id_for_update.return_value = req
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)

    with pytest.raises(PermissionDeniedError):
        await service.invite_user_to_team(
            team_id=team.id,
            captain_id=regular_member.id,
            target_user_id=solo_student.id,
        )

    with pytest.raises(PermissionDeniedError):
        await service.captain_approve_request(
            request_id=req.id,
            captain_id=regular_member.id,
        )


# ------------------------------------------------------------------
# 6. Овербукинг при уменьшении глобального лимита event.max_team_size
# ------------------------------------------------------------------


async def test_adv_req_user_confirm_respects_shrunk_event_max_team_size(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 5.1 (п. 6): лимит проверяется по min(team.max_members, event.max_team_size).
    Если у команды max_members=5, но организатор снизил event.max_team_size до 3 и в команде уже 3 человека,
    подтверждение оффера выбрасывает TeamIsFullError (409)."""
    event = make_event(min_team_size=2, max_team_size=3)
    captain = make_user()
    student = make_user()
    team = make_team(event, captain, max_members=5)
    reg = make_registration(student, event)
    req = make_team_request(
        event, team, student, status=TeamRequestStatus.PENDING_USER
    )

    fake_uow.requests.get_by_id_for_update.return_value = req
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = reg
    fake_uow.teams.get_members_count.return_value = 3  # Достигнут event.max_team_size=3

    service = TeamServices(fake_uow)

    with pytest.raises(TeamIsFullError):
        await service.user_confirm_request(request_id=req.id, user_id=student.id)


# ------------------------------------------------------------------
# 7. Безопасность схемы TeamRequestRead в GET /events/{id}/my-requests
# ------------------------------------------------------------------


async def test_adv_req_my_requests_endpoint_includes_team_name_and_hides_private_user_data(
    async_client: AsyncClient,
):
    """SPEC 2.4 & 6.4: роут GET /events/{id}/my-requests возвращает team_name и профиль кандидата
    БЕЗ приватных полей (email, telegram_id, hashed_password, is_superuser)."""
    event = make_event()
    captain = make_user()
    candidate = make_user(
        email="private_candidate@sfu.ru",
        telegram_id=123456789,
        is_superuser=True,
    )
    team = make_team(event, captain, name="Cyber Bears")
    req = make_team_request(
        event,
        team,
        candidate,
        message="Возьмите в команду",
        target_role=ParticipantSpecialization.BACKEND.value,
        status=TeamRequestStatus.PENDING_CAPTAIN,
    )

    mock_service = AsyncMock()
    mock_service.get_my_requests.return_value = [req]

    app.dependency_overrides[current_user] = lambda: captain
    app.dependency_overrides[team_service] = lambda: mock_service

    response = await async_client.get(f"/api/v1/events/{event.id}/my-requests")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    item = items[0]
    assert item["team_name"] == "Cyber Bears"
    assert item["user"]["full_name"] == candidate.full_name
    assert "email" not in item["user"]
    assert "telegram_id" not in item["user"]
    assert "hashed_password" not in item["user"]
    assert "is_superuser" not in item["user"]


# ------------------------------------------------------------------
# 8. Rate Limiting на /apply должен считаться НА ПОЛЬЗОВАТЕЛЯ, а не на общий IP (SPEC 6.1)
# ------------------------------------------------------------------


async def test_adv_req_rate_limit_apply_is_per_user_and_returns_429(
    async_client: AsyncClient,
):
    """SPEC 6.1: лимит POST /teams/{team_id}/apply — 20 req/min НА ПОЛЬЗОВАТЕЛЯ.
    Когда user_1 исчерпал свои 20 попыток и получил 429, user_2 с того же IP (например, Wi-Fi вуза)
    должен успешно отправить заявку (200 OK)."""
    event = make_event()
    captain = make_user()
    user_1 = make_user(email="spammer@sfu.ru")
    user_2 = make_user(email="honest@sfu.ru")
    team = make_team(event, captain)
    dummy_req = make_team_request(event, team, user_1)

    mock_service = AsyncMock()
    mock_service.apply_to_team.return_value = dummy_req
    app.dependency_overrides[team_service] = lambda: mock_service

    # 1. Пользователь 1 делает 20 разрешенных запросов, 21-й должен вернуть 429
    app.dependency_overrides[current_user] = lambda: user_1
    statuses_user_1 = []
    for _ in range(21):
        res = await async_client.post(f"/api/v1/teams/{team.id}/apply")
        statuses_user_1.append(res.status_code)

    assert statuses_user_1[:20] == [200] * 20
    assert statuses_user_1[20] == 429, "21-й запрос от одного пользователя должен вернуть 429 Too Many Requests"

    # 2. Пользователь 2 с того же самого IP отправляет свой 1-й запрос — он НЕ должен блокироваться!
    app.dependency_overrides[current_user] = lambda: user_2
    res_user_2 = await async_client.post(f"/api/v1/teams/{team.id}/apply")
    assert res_user_2.status_code == 200, (
        "Лимитер заблокировал другого пользователя по общему IP! По SPEC 6.1 лимит /apply должен быть на пользователя."
    )


# ------------------------------------------------------------------
# 9. Rate Limiting на POST /api/v1/auth/jwt/login — 10 req/min с одного IP (SPEC 6.1)
# ------------------------------------------------------------------


async def test_adv_req_login_rate_limited_to_10_per_minute(
    async_client: AsyncClient,
):
    """SPEC 6.1: POST /api/v1/auth/jwt/login ограничен 10 запросами в минуту с одного IP."""
    from auth.manager import get_user_manager

    mock_user_manager = AsyncMock()
    mock_user_manager.authenticate.return_value = None
    app.dependency_overrides[get_user_manager] = lambda: mock_user_manager

    statuses = []
    for _ in range(11):
        res = await async_client.post(
            "/api/v1/auth/jwt/login",
            data={"username": "wrong@sfu.ru", "password": "wrongpassword"},
        )
        statuses.append(res.status_code)

    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429
    