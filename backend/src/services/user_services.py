"""Сервисный слой для работы с профилями пользователей и привязкой Telegram."""

import secrets
import uuid
from typing import Optional

from auth.auth import password_helper
from auth.schemas import UserUpdate
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
        """Обновить профиль пользователя."""
        async with self.uow:
            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            update_data = user_data.model_dump(exclude_unset=True)

            # Если передан пароль — хэшируем его в hashed_password
            if "password" in update_data:
                password = update_data.pop("password")
                if password:
                    update_data["hashed_password"] = password_helper.hash(password)

            # Пользователь не может сам себе выдать права админа через обновление профиля
            update_data.pop("is_superuser", None)
            update_data.pop("is_verified", None)

            # Фильтруем только те поля, которые реально существуют в таблице User
            valid_columns = {c.name for c in self.uow.users.model.__table__.columns}
            filtered_data = {k: v for k, v in update_data.items() if k in valid_columns}

            updated_user = await self.uow.users.update(user_id, filtered_data)
            await self.uow.commit()
            return updated_user

    async def generate_telegram_bind_link(self, user_id: uuid.UUID) -> str:
        """Сгенерировать одноразовую deep-link ссылку для привязки Telegram-бота."""
        async with self.uow:
            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            bind_token = f"bind_{secrets.token_hex(16)}"
            await self.uow.users.update(user_id, {"telegram_bind_token": bind_token})
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
                raise InvalidStateError("Недействительный или истекший токен привязки Telegram")

            # Проверяем, не привязан ли этот Telegram ID к другому пользователю
            existing_user = await self.uow.users.find_one_or_none(telegram_id=telegram_id)
            if existing_user and existing_user.id != user.id:
                raise InvalidStateError("Данный Telegram-аккаунт уже привязан к другому профилю")

            update_data = {
                "telegram_id": telegram_id,
                "telegram_username": telegram_username,
                "is_bot_active": True,
                "telegram_bind_token": None,
            }
            updated_user = await self.uow.users.update(user.id, update_data)
            await self.uow.commit()
            return updated_user
