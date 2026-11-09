"""Сервисный слой для работы с профилями пользователей и привязкой Telegram."""

from datetime import datetime, timedelta, timezone
import secrets
import uuid
from typing import Optional

from auth.auth import password_helper
from auth.schemas import UserPasswordChange, UserUpdate
from config import BOT_USERNAME
from models.user import User
from utils.exceptions import EntityNotFoundError, InvalidStateError
from utils.uow import IUnitOfWork


class UserServices:
    """Сервис управления пользователями и интеграцией с Telegram."""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        """Получить пользователя по ID."""
        async with self.uow:
            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")
            return user

    async def update_profile(self, user_id: uuid.UUID, user_data: UserUpdate) -> User:
        """Обновить поля профиля пользователя (без смены пароля)."""
        async with self.uow:
            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            update_data = user_data.model_dump(exclude_unset=True)
            updated_user = await self.uow.users.update(user_id, update_data)
            await self.uow.commit()
            return updated_user

    async def change_password(
        self,
        user_id: uuid.UUID,
        password_data: UserPasswordChange,
    ) -> None:
        """Безопасная смена пароля с подтверждением старого пароля."""
        async with self.uow:
            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            # 1. Проверяем корректность старого пароля
            verified, _ = password_helper.verify_and_update(
                password_data.old_password, user.hashed_password
            )
            if not verified:
                raise InvalidStateError("Неверный текущий пароль")

            # 2. Новый пароль не должен совпадать с текущим
            if password_data.old_password == password_data.new_password:
                raise InvalidStateError("Новый пароль не должен совпадать с текущим")

            # 3. Хэшируем и сохраняем новый пароль
            hashed_password = password_helper.hash(password_data.new_password)
            await self.uow.users.update(user_id, {"hashed_password": hashed_password})
            await self.uow.commit()

    async def generate_telegram_bind_link(self, user_id: uuid.UUID) -> str:
        """Сгенерировать одноразовую deep-link ссылку для привязки Telegram-бота с TTL 15 минут."""
        async with self.uow:
            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            bind_token = f"bind_{secrets.token_hex(16)}"
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            await self.uow.users.update(
                user_id,
                {
                    "telegram_bind_token": bind_token,
                    "telegram_bind_token_expires_at": expires_at,
                },
            )
            await self.uow.commit()

            bot_name = BOT_USERNAME.lstrip("@")
            return f"https://t.me/{bot_name}?start={bind_token}"

    async def bind_telegram(
        self,
        token: str,
        telegram_id: int,
        telegram_username: Optional[str],
    ) -> User:
        """Привязать Telegram-аккаунт к пользователю по одноразовому токену."""
        async with self.uow:
            user = await self.uow.users.find_one_or_none(telegram_bind_token=token)
            if not user:
                raise InvalidStateError(
                    "Недействительный или истекший токен привязки Telegram"
                )

            # Проверяем срок жизни токена (TTL 15 минут)
            if user.telegram_bind_token_expires_at:
                now = datetime.now(timezone.utc)
                if now > user.telegram_bind_token_expires_at:
                    raise InvalidStateError(
                        "Срок действия токена привязки Telegram истек (15 минут). Запросите новую ссылку в личном кабинете."
                    )

            # Проверяем, не привязан ли этот Telegram ID к другому пользователю
            existing_user = await self.uow.users.find_one_or_none(
                telegram_id=telegram_id
            )
            if existing_user and existing_user.id != user.id:
                raise InvalidStateError(
                    "Данный Telegram-аккаунт уже привязан к другому профилю"
                )

            update_data = {
                "telegram_id": telegram_id,
                "telegram_username": telegram_username,
                "is_bot_active": True,
                "telegram_bind_token": None,
                "telegram_bind_token_expires_at": None,
            }
            updated_user = await self.uow.users.update(user.id, update_data)
            await self.uow.commit()
            return updated_user
