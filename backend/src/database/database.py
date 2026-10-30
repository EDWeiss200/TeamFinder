"""Настройка базы данных и сессий SQLAlchemy."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL_CONFIG

DATABASE_URL = DATABASE_URL_CONFIG


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Генератор асинхронных сессий базы данных."""
    async with async_session_maker() as session:
        yield session
