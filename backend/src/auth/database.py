"""Адаптер базы данных для fastapi-users."""

from typing import AsyncGenerator
from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_async_session
from models.user import User


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """Предоставляет адаптер БД для fastapi-users с моделью User."""
    yield SQLAlchemyUserDatabase(session, User)
