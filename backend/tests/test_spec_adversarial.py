# Файл: backend/tests/test_spec_adversarial.py
"""Каверзные (adversarial) тесты по спецификации SPEC_2.md для поиска скрытых багов Фаз 1–4."""

import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from httpx import AsyncClient
from PIL import Image
from pydantic import ValidationError
from starlette.datastructures import Headers

from api.dependencies import event_service, team_service
from auth.auth import current_user
from auth.schemas import UserUpdate
from main import app
from models.enums import EventStatus, UserRole
from schemas.event import EventCreate, EventRegistrationCreate
from schemas.team import TeamCreate, TeamDetailRead, TeamUpdate
from services.event_services import EventServices
from services.team_services import TeamServices
from services.upload_services import UploadServices
from services.user_services import UserServices
from tests.conftest import (
    FakeUnitOfWork,
    make_event,
    make_registration,
    make_team,
    make_user,
)
from utils.exceptions import (
    DeadlinePassedError,
    EntityNotFoundError,
    InvalidStateError,
    PermissionDeniedError,
)


# ------------------------------------------------------------------
# 1. Загрузка медиа: обязательная конвертация PNG/JPEG -> WebP (Раздел 6.1)
# ------------------------------------------------------------------


async def test_adv_upload_png_must_convert_to_webp(tmp_path: Path):
    """SPEC 6.1: загруженный PNG обязан конвертироваться в формат WebP и иметь расширение .webp."""
    service = UploadServices(upload_dir=tmp_path)

    buf = io.BytesIO()
    Image.new("RGBA", (32, 32), color=(255, 0, 0, 128)).save(buf, format="PNG")
    upload = UploadFile(
        file=io.BytesIO(buf.getvalue()),
        filename="avatar.png",
        headers=Headers({"content-type": "image/png"}),
    )

    url = await service.save_image(upload)

    # 1. Ссылка должна заканчиваться на .webp
    assert url.endswith(".webp"), f"Ожидался .webp URL по SPEC 6.1, получен: {url}"

    # 2. Файл на диске должен реально иметь формат WEBP, а не просто переименованный PNG
    saved_path = tmp_path / url.split("/")[-1]
    with Image.open(saved_path) as saved_img:
        assert saved_img.format == "WEBP", f"Файл не сконвертирован в WEBP (формат: {saved_img.format})"


# ------------------------------------------------------------------
# 2. Безопасность черновиков: DRAFT виден только организатору (Раздел 4.1)
# ------------------------------------------------------------------


async def test_adv_draft_event_hidden_from_regular_participant(fake_uow: FakeUnitOfWork):
    """SPEC 4.1: мероприятие в статусе DRAFT не должно открываться обычным участникам или анонимам."""
    organizer_id = uuid.uuid4()
    regular_student = make_user(role=UserRole.PARTICIPANT)
    draft_event = make_event(
        organizer_id=organizer_id,
        status=EventStatus.DRAFT,
        is_public=False,
    )
    fake_uow.events.get_by_id_or_invite_code.return_value = draft_event

    service = EventServices(fake_uow)

    with pytest.raises((EntityNotFoundError, PermissionDeniedError)):
        await service.get_event_detail(
            identifier=str(draft_event.id),
            current_user_id=regular_student.id,
        )


# ------------------------------------------------------------------
# 3. Коллизия ленивого дедлайна и фильтра каталога (Разделы 5.2 и 6.2)
# ------------------------------------------------------------------


async def test_adv_public_events_filter_registration_excludes_lazily_expired(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 5.2 & 6.2: если при запросе GET /events?status=registration у события истек дедлайн,
    оно переходит в TEAM_LOCK и НЕ должно возвращаться в выдаче как активное для регистрации."""
    past = datetime.now(timezone.utc) - timedelta(minutes=15)
    expired_event = make_event(
        status=EventStatus.REGISTRATION,
        registration_end=past,
    )
    fake_uow.events.get_public_events.return_value = [expired_event]
    fake_uow.events.count_public_events.return_value = 0

    service = EventServices(fake_uow)
    result = await service.get_public_events(
        status=EventStatus.REGISTRATION,
        page=1,
        size=20,
    )

    assert all(
        ev.status == EventStatus.REGISTRATION for ev in result.items
    ), "В выборку со строгим фильтром status=REGISTRATION попал ивент со статусом TEAM_LOCK!"


# ------------------------------------------------------------------
# 4. HTTP 422 при незаполненной анкете хакатона (Раздел 6.2)
# ------------------------------------------------------------------


async def test_adv_register_missing_required_custom_field_returns_422(
    async_client: AsyncClient,
    fake_uow: FakeUnitOfWork,
):
    """SPEC 6.2: если не заполнено обязательное поле custom_fields_schema, возвращается 422 Unprocessable Entity."""
    user = make_user()
    event = make_event(
        custom_fields_schema=[
            {"id": "passport", "label": "Серия и номер паспорта", "type": "text", "required": True}
        ]
    )
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user.return_value = None

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[event_service] = lambda: EventServices(fake_uow)

    response = await async_client.post(
        f"/api/v1/events/{event.id}/register",
        json={"custom_answers": {}},
    )

    assert response.status_code == 422, (
        f"По SPEC 6.2 ожидался код 422 Unprocessable Entity, но сервер вернул {response.status_code}"
    )


# ------------------------------------------------------------------
# 5. HTTP 409 при вступлении по токену после закрытия регистрации (Раздел 2.4 Сценарий В)
# ------------------------------------------------------------------


async def test_adv_join_by_token_when_registration_closed_returns_409(
    async_client: AsyncClient,
    fake_uow: FakeUnitOfWork,
):
    """SPEC 2.4 (Сценарий В, п. 4): если event.status != REGISTRATION, возвращается 409 Conflict."""
    user = make_user()
    event = make_event(status=EventStatus.TEAM_LOCK)
    captain = make_user()
    team = make_team(event, captain, invite_token="valid-token")

    fake_uow.teams.get_by_invite_token_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[team_service] = lambda: TeamServices(fake_uow)

    response = await async_client.post("/api/v1/teams/join-by-token/valid-token")

    assert response.status_code == 409, (
        f"По SPEC 2.4 (Сценарий В) при закрытой регистрации ожидается 409 Conflict, получен {response.status_code}"
    )


# ------------------------------------------------------------------
# 6. Запрет капитану менять команду после дедлайна регистрации (Раздел 5.2)
# ------------------------------------------------------------------


async def test_adv_captain_cannot_update_team_when_registration_deadline_passed(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 5.2: после истечения registration_end (переход в TEAM_LOCK) капитан больше не может редактировать команду."""
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    event = make_event(status=EventStatus.REGISTRATION, registration_end=past)
    captain = make_user()
    team = make_team(event, captain)

    fake_uow.teams.get_by_id_with_members.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)

    with pytest.raises((InvalidStateError, DeadlinePassedError, PermissionDeniedError)):
        await service.update_team(
            team_id=team.id,
            actor_user=captain,
            update_data=TeamUpdate(name="Late Rename"),
        )


# ------------------------------------------------------------------
# 7. Запрет перевыпуска invite_token после заморозки команд (Раздел 5.2)
# ------------------------------------------------------------------


async def test_adv_captain_cannot_regenerate_invite_token_in_team_lock(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 5.2: в фазе TEAM_LOCK или FINISHED перевыпуск инвайт-токена капитаном должен быть запрещен."""
    event = make_event(status=EventStatus.TEAM_LOCK)
    captain = make_user()
    team = make_team(event, captain)

    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)

    with pytest.raises((InvalidStateError, DeadlinePassedError)):
        await service.regenerate_invite_token(
            team_id=team.id,
            actor_user_id=captain.id,
        )


# ------------------------------------------------------------------
# 8. Запрет специализаций разработчика для роли ORGANIZER (Разделы 2.2, 4.1, 4.2)
# ------------------------------------------------------------------


async def test_adv_organizer_must_have_empty_specializations(fake_uow: FakeUnitOfWork):
    """SPEC 2.2 & 4.1: для пользователей с ролью ORGANIZER массив specializations обязан оставаться пустым []."""
    organizer = make_user(role=UserRole.ORGANIZER, specializations=[])
    fake_uow.users.find_one_or_none.return_value = organizer
    fake_uow.users.update.side_effect = lambda uid, data: make_user(
        id=uid, role=UserRole.ORGANIZER, **data
    )

    service = UserServices(fake_uow)

    # Либо выбрасывается ошибка, либо specializations принудительно очищается в []
    try:
        updated = await service.update_profile(
            organizer.id,
            UserUpdate(specializations=["backend", "frontend"]),
        )
        assert updated.specializations == [], (
            "Организатору удалось сохранить специализации разработчика, хотя по SPEC 2.2 должен быть []"
        )
    except InvalidStateError:
        pass


# ------------------------------------------------------------------
# 9. Маскирование invite_token по умолчанию в схеме TeamDetailRead (Раздел 2.4 и 6.3)
# ------------------------------------------------------------------


def test_adv_team_detail_read_masks_invite_token_by_default():
    """SPEC 2.4 & 6.3: прямая валидация ORM-объекта через TeamDetailRead не должна сливать invite_token."""
    event = make_event()
    captain = make_user()
    team = make_team(event, captain, invite_token="super-secret-token")

    dto = TeamDetailRead.model_validate(team)

    assert dto.invite_token is None, (
        "Утечка безопасности: TeamDetailRead.model_validate(team) раскрывает invite_token по умолчанию!"
    )


# ------------------------------------------------------------------
# 10. Запрет названия команды из одних пробелов (Раздел 4.2 и 6.3)
# ------------------------------------------------------------------


def test_adv_team_create_rejects_whitespace_only_name():
    """Название команды не может состоять только из пробелов ('   ')."""
    with pytest.raises(ValidationError):
        TeamCreate(
            name="     ",
            max_members=4,
            needed_roles=["backend"],
        )


# ------------------------------------------------------------------
# 11. Хронология дат и лимитов команды при создании события (Раздел 4.2)
# ------------------------------------------------------------------


def test_adv_event_create_rejects_inverted_dates_and_team_sizes():
    """SPEC 4.2: в EventCreate дата окончания регистрации не может быть раньше начала, а min_team_size > max_team_size."""
    now = datetime.now(timezone.utc)

    # 1. Инвертированные даты регистрации
    with pytest.raises(ValidationError):
        EventCreate(
            title="Bad Dates Hack",
            short_description="Кратко",
            description_md="# Полное",
            organizer_name="СФУ",
            min_team_size=2,
            max_team_size=5,
            registration_start=now + timedelta(days=5),
            registration_end=now + timedelta(days=1),  # Раньше старта!
            event_start=now + timedelta(days=6),
            submission_deadline=now + timedelta(days=7),
            event_end=now + timedelta(days=8),
        )

    # 2. min_team_size больше max_team_size
    with pytest.raises(ValidationError):
        EventCreate(
            title="Bad Limits Hack",
            short_description="Кратко",
            description_md="# Полное",
            organizer_name="СФУ",
            min_team_size=6,
            max_team_size=3,  # Меньше минимума!
            registration_start=now,
            registration_end=now + timedelta(days=2),
            event_start=now + timedelta(days=3),
            submission_deadline=now + timedelta(days=4),
            event_end=now + timedelta(days=5),
        )


# ------------------------------------------------------------------
# 12. Закрытие роли самого капитана при создании команды (Раздел 2.3 и 5.1)
# ------------------------------------------------------------------


async def test_adv_create_team_captain_specialization_vs_needed_roles(
    fake_uow: FakeUnitOfWork,
):
    """SPEC 2.3: если капитан с ролью 'backend' при создании команды из 2 человек указал
    needed_roles=['backend', 'backend', 'frontend'], проверяем корректность инициализации состава."""
    event = make_event(min_team_size=2, max_team_size=3)
    captain = make_user(specializations=["backend"])
    reg = make_registration(captain, event)
    created_team = make_team(event, captain, max_members=2, needed_roles=["backend", "frontend"])

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = reg
    fake_uow.teams.is_name_taken.return_value = False
    fake_uow.teams.find_one_or_none.return_value = None
    fake_uow.teams.add_one.return_value = created_team
    fake_uow.teams.get_by_id_with_members.return_value = created_team

    service = TeamServices(fake_uow)

    # Команда на 2 человек (1 место уже занято капитаном -> остался 1 свободный слот),
    # значит список needed_roles («Ищем») не может содержать 3 искомые роли при 1 свободном слоте!
    with pytest.raises((InvalidStateError, ValidationError)):
        await service.create_team(
            event_id=event.id,
            creator_id=captain.id,
            team_data=TeamCreate(
                name="OverRole Team",
                max_members=2,
                needed_roles=["backend", "frontend", "design"],  # 3 роли на 1 свободное место!
            ),
        )