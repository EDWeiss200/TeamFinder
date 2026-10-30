"""Модуль аутентификации и JWT-стратегии fastapi-users."""

import uuid
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.password import PasswordHelper
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from auth.manager import get_user_manager
from config import COOKIE_SECURE, SECRET_AUTH
from models.user import User

# Транспорт через Cookies (с учетом флага COOKIE_SECURE для локальной разработки)
cookie_samesite = "none" if COOKIE_SECURE else "lax"
cookie_transport = CookieTransport(
    cookie_name="teamtinder_session",
    cookie_max_age=28800,
    cookie_secure=COOKIE_SECURE,
    cookie_samesite=cookie_samesite,
)

# Транспорт через заголовок Authorization: Bearer <token>
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    """Генератор стратегии JWT с временем жизни токена 24 часа."""
    return JWTStrategy(secret=SECRET_AUTH, lifetime_seconds=86400)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

bearer_backend = AuthenticationBackend(
    name="jwt-bearer",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend, bearer_backend],
)

# Хэширование паролей с алгоритмом Argon2
password_hash = PasswordHash((Argon2Hasher(),))
password_helper = PasswordHelper(password_hash)

# Текущий авторизованный активный пользователь
current_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
