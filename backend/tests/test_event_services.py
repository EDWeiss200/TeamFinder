# Файл: backend/tests/test_event_services.py
"""Модульные тесты для EventServices (ленивые дедлайны, анкеты, регистрация)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.enums import EventStatus
from schemas.event import EventRegistrationCreate
from services.event_services import EventServices
from tests.conftest import FakeUnitOfWork, make_event, make_registration, make_user
from utils.exceptions import EntityNotFoundError, InvalidStateError


# ------------------------------------------------------------------
# Тесты ленивой смены статусов (Lazy Status Transitions)
# ------------------------------------------------------------------


async def test_lazy_transition_registration_to_team_lock(fake_uow: FakeUnitOfWork):
    """Если registration_end в прошлом, статус переходит в TEAM_LOCK, а висящие заявки отменяются."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    event = make_event(status=EventStatus.REGISTRATION, registration_end=past)
    fake_uow.events.get_by_id_or_invite_code.return_value = event

    service = EventServices(fake_uow)
    res = await service.get_event_detail(identifier=str(event.id))

    assert res["event"].status == EventStatus.TEAM_LOCK
    fake_uow.events.update.assert_awaited_once_with(
        event.id, {"status": EventStatus.TEAM_LOCK}
    )
    fake_uow.requests.cancel_all_event_pending_requests.assert_awaited_once_with(event.id)
    assert fake_uow.committed is True


async def test_lazy_transition_submission_to_finished(fake_uow: FakeUnitOfWork):
    """Если submission_deadline в прошлом, статус SUBMISSION автоматически переходит в FINISHED."""
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    event = make_event(status=EventStatus.SUBMISSION, submission_deadline=past)
    fake_uow.events.get_by_id_or_invite_code.return_value = event

    service = EventServices(fake_uow)
    res = await service.get_event_detail(identifier=event.invite_code)

    assert res["event"].status == EventStatus.FINISHED
    fake_uow.events.update.assert_awaited_once_with(
        event.id, {"status": EventStatus.FINISHED}
    )
    assert fake_uow.committed is True


# ------------------------------------------------------------------
# Тесты валидации кастомных полей анкеты (custom_fields_schema)
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "answers, should_pass",
    [
        ({"tshirt": "L", "diet": "Нет"}, True),
        ({"tshirt": "M"}, True),                    # Поле diet необязательное
        ({"tshirt": "XXL"}, False),                 # XXL нет в списке options
        ({}, False),                                # Отсутствует обязательное поле tshirt
        ({"tshirt": "   "}, False),                 # Пустая строка из пробелов в обязательном поле
    ],
)
def test_validate_custom_answers(
    fake_uow: FakeUnitOfWork,
    answers: dict,
    should_pass: bool,
):
    """Проверяет валидацию обязательных полей и выпадающих списков (select) анкеты хакатона."""
    schema = [
        {
            "id": "tshirt",
            "label": "Размер футболки",
            "type": "select",
            "options": ["S", "M", "L", "XL"],
            "required": True,
        },
        {
            "id": "diet",
            "label": "Предпочтения по еде",
            "type": "text",
            "required": False,
        },
    ]
    service = EventServices(fake_uow)

    if should_pass:
        service._validate_custom_answers(schema, answers)
    else:
        with pytest.raises(InvalidStateError):
            service._validate_custom_answers(schema, answers)


# ------------------------------------------------------------------
# Тесты регистрации на мероприятие (register_for_event)
# ------------------------------------------------------------------


async def test_register_for_event_success(fake_uow: FakeUnitOfWork):
    """Успешная регистрация участника на активное мероприятие."""
    user = make_user()
    event = make_event(
        custom_fields_schema=[
            {"id": "laptop", "label": "Ноутбук", "type": "select", "options": ["Да", "Нет"], "required": True}
        ]
    )
    expected_reg = make_registration(user, event, custom_answers={"laptop": "Да"})

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user.return_value = None
    fake_uow.registrations.add_one.return_value = expected_reg

    service = EventServices(fake_uow)
    reg = await service.register_for_event(
        event_id=event.id,
        user_id=user.id,
        registration_data=EventRegistrationCreate(custom_answers={"laptop": "Да"}),
    )

    assert reg.user_id == user.id
    assert fake_uow.committed is True


async def test_register_for_event_duplicate_rejected(fake_uow: FakeUnitOfWork):
    """Повторная регистрация того же участника выбрасывает InvalidStateError."""
    user = make_user()
    event = make_event()
    existing_reg = make_registration(user, event)

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user.return_value = existing_reg

    service = EventServices(fake_uow)
    with pytest.raises(InvalidStateError, match="уже зарегистрированы"):
        await service.register_for_event(
            event_id=event.id,
            user_id=user.id,
            registration_data=EventRegistrationCreate(),
        )


async def test_register_for_event_closed_when_deadline_passed(fake_uow: FakeUnitOfWork):
    """Если дедлайн регистрации истек, событие переводится в TEAM_LOCK и регистрация отклоняется."""
    user = make_user()
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    event = make_event(status=EventStatus.REGISTRATION, registration_end=past)

    fake_uow.events.find_one_or_none.return_value = event
    service = EventServices(fake_uow)

    with pytest.raises(InvalidStateError, match="Регистрация на это мероприятие закрыта"):
        await service.register_for_event(
            event_id=event.id,
            user_id=user.id,
            registration_data=EventRegistrationCreate(),
        )
    assert event.status == EventStatus.TEAM_LOCK


async def test_get_solo_participants_not_found_event(fake_uow: FakeUnitOfWork):
    """Запрос каталога одиночек для несуществующего хакатона выбрасывает EntityNotFoundError."""
    fake_uow.events.find_one_or_none.return_value = None
    service = EventServices(fake_uow)

    with pytest.raises(EntityNotFoundError):
        await service.get_solo_participants(event_id=uuid.uuid4())