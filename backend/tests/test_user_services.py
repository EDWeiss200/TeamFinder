# Файл: backend/tests/test_user_services.py
"""Модульные тесты для UserServices."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from auth.auth import password_helper
from auth.schemas import UserPasswordChange, UserUpdate
from services.user_services import UserServices
from tests.conftest import FakeUnitOfWork, make_user
from utils.exceptions import EntityNotFoundError, InvalidStateError


async def test_get_user_by_id_success(fake_uow: FakeUnitOfWork):
    """Успешное получение пользователя по ID."""
    expected_user = make_user()
    fake_uow.users.find_one_or_none.return_value = expected_user

    service = UserServices(fake_uow)
    result = await service.get_user_by_id(expected_user.id)

    assert result == expected_user
    fake_uow.users.find_one_or_none.assert_awaited_once_with(id=expected_user.id)


async def test_get_user_by_id_not_found(fake_uow: FakeUnitOfWork):
    """Если пользователь не найден, выбрасывается EntityNotFoundError."""
    fake_uow.users.find_one_or_none.return_value = None
    service = UserServices(fake_uow)

    with pytest.raises(EntityNotFoundError):
        await service.get_user_by_id(uuid.uuid4())


async def test_update_profile_success(fake_uow: FakeUnitOfWork):
    """Обновление профиля передает только измененные поля (exclude_unset=True) и делает commit."""
    user = make_user(nickname="old_nick")
    updated_user = make_user(id=user.id, nickname="new_nick", course=3)
    fake_uow.users.find_one_or_none.return_value = user
    fake_uow.users.update.return_value = updated_user

    service = UserServices(fake_uow)
    patch_data = UserUpdate(nickname="new_nick", course=3)
    result = await service.update_profile(user.id, patch_data)

    assert result.nickname == "new_nick"
    assert fake_uow.committed is True
    fake_uow.users.update.assert_awaited_once_with(
        user.id, {"nickname": "new_nick", "course": 3}
    )


async def test_change_password_success(fake_uow: FakeUnitOfWork):
    """Успешная смена пароля при верном старом пароле."""
    old_plain = "OldSecret123!"
    new_plain = "NewSecret456!"
    user = make_user(hashed_password=password_helper.hash(old_plain))
    fake_uow.users.find_one_or_none.return_value = user

    service = UserServices(fake_uow)
    await service.change_password(
        user.id,
        UserPasswordChange(old_password=old_plain, new_password=new_plain),
    )

    assert fake_uow.committed is True
    fake_uow.users.update.assert_awaited_once()
    saved_hash = fake_uow.users.update.call_args[0][1]["hashed_password"]
    verified, _ = password_helper.verify_and_update(new_plain, saved_hash)
    assert verified is True


async def test_change_password_wrong_old_password(fake_uow: FakeUnitOfWork):
    """Ошибка InvalidStateError, если старый пароль введен неверно."""
    user = make_user(hashed_password=password_helper.hash("CorrectPass123"))
    fake_uow.users.find_one_or_none.return_value = user

    service = UserServices(fake_uow)
    with pytest.raises(InvalidStateError, match="Неверный текущий пароль"):
        await service.change_password(
            user.id,
            UserPasswordChange(
                old_password="WrongPass000", new_password="NewPass12345"
            ),
        )
    assert fake_uow.committed is False


async def test_change_password_same_as_old(fake_uow: FakeUnitOfWork):
    """Ошибка InvalidStateError, если новый пароль совпадает со старым."""
    same_pass = "SamePassword123"
    user = make_user(hashed_password=password_helper.hash(same_pass))
    fake_uow.users.find_one_or_none.return_value = user

    service = UserServices(fake_uow)
    with pytest.raises(InvalidStateError, match="не должен совпадать"):
        await service.change_password(
            user.id,
            UserPasswordChange(old_password=same_pass, new_password=same_pass),
        )


async def test_generate_telegram_bind_link(fake_uow: FakeUnitOfWork):
    """Генерация ссылки сохраняет токен с префиксом bind_ и TTL 15 минут."""
    user = make_user()
    fake_uow.users.find_one_or_none.return_value = user

    service = UserServices(fake_uow)
    link = await service.generate_telegram_bind_link(user.id)

    assert "?start=bind_" in link
    assert fake_uow.committed is True
    update_payload = fake_uow.users.update.call_args[0][1]
    assert update_payload["telegram_bind_token"].startswith("bind_")
    assert update_payload["telegram_bind_token_expires_at"] > datetime.now(timezone.utc)


async def test_bind_telegram_success(fake_uow: FakeUnitOfWork):
    """Успешная привязка Telegram по валидному токену и сброс одноразового токена."""
    now = datetime.now(timezone.utc)
    user = make_user(
        telegram_bind_token="bind_valid123",
        telegram_bind_token_expires_at=now + timedelta(minutes=10),
    )
    # 1-й вызов find_one_or_none — поиск по токену, 2-й — проверка занятости telegram_id
    fake_uow.users.find_one_or_none.side_effect = [user, None]
    fake_uow.users.update.return_value = user

    service = UserServices(fake_uow)
    await service.bind_telegram(
        token="bind_valid123",
        telegram_id=999888777,
        telegram_username="grisha_new",
    )

    assert fake_uow.committed is True
    update_payload = fake_uow.users.update.call_args[0][1]
    assert update_payload["telegram_id"] == 999888777
    assert update_payload["is_bot_active"] is True
    assert update_payload["telegram_bind_token"] is None
    assert update_payload["telegram_bind_token_expires_at"] is None


async def test_bind_telegram_expired_token(fake_uow: FakeUnitOfWork):
    """Если прошло больше 15 минут, привязка отклоняется с InvalidStateError."""
    expired_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    user = make_user(
        telegram_bind_token="bind_expired",
        telegram_bind_token_expires_at=expired_time,
    )
    fake_uow.users.find_one_or_none.return_value = user

    service = UserServices(fake_uow)
    with pytest.raises(InvalidStateError, match="Срок действия токена"):
        await service.bind_telegram("bind_expired", 12345, "user")

    assert fake_uow.committed is False


async def test_bind_telegram_already_linked_to_another_user(fake_uow: FakeUnitOfWork):
    """Запрет привязки одного Telegram-аккаунта к двум разным профилям."""
    now = datetime.now(timezone.utc)
    user1 = make_user(
        telegram_bind_token="bind_tok",
        telegram_bind_token_expires_at=now + timedelta(minutes=10),
    )
    user2 = make_user(telegram_id=555555)
    fake_uow.users.find_one_or_none.side_effect = [user1, user2]

    service = UserServices(fake_uow)
    with pytest.raises(InvalidStateError, match="уже привязан к другому профилю"):
        await service.bind_telegram("bind_tok", 555555, "user")
