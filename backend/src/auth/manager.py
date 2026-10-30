"""Менеджер управления пользователями fastapi-users."""

import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions, models, schemas

from auth.database import get_user_db
from config import SECRET_USER_MANAGER
from models.user import User

SECRET = SECRET_USER_MANAGER


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Менеджер жизненного цикла пользователя (регистрация, сброс пароля, верификация)."""

    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Хэндлер после успешной регистрации пользователя."""
        print(f"Пользователь {user.id} ({user.email}) успешно зарегистрирован.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Хэндлер запроса сброса пароля."""
        print(f"Пользователь {user.id} запросил сброс пароля. Токен: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Хэндлер запроса верификации email."""
        print(f"Запрошена верификация для пользователя {user.id}. Токен: {token}")

    async def create(
        self,
        user_create: schemas.UC,
        safe: bool = False,
        request: Optional[Request] = None,
    ) -> models.UP:
        """Создание пользователя с валидацией пароля и хэшированием."""
        await self.validate_password(user_create.password, user_create)

        existing_user = await self.user_db.get_by_email(user_create.email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        user_dict = (
            user_create.create_update_dict()
            if safe
            else user_create.create_update_dict_superuser()
        )
        password = user_dict.pop("password")
        user_dict["hashed_password"] = self.password_helper.hash(password)

        created_user = await self.user_db.create(user_dict)
        await self.on_after_register(created_user, request)
        return created_user


async def get_user_manager(user_db=Depends(get_user_db)):
    """Фабрика зависимости менеджера пользователей."""
    yield UserManager(user_db)
