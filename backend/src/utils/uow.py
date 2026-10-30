"""Паттерн Unit of Work для управления транзакциями базы данных."""

from abc import ABC, abstractmethod
from database.database import async_session_maker
from repositories.user_repo import UserRepository


class IUnitOfWork(ABC):
    """Интерфейс единицы работы (Unit of Work)."""

    users: UserRepository

    @abstractmethod
    def __init__(self): ...

    @abstractmethod
    async def __aenter__(self): ...

    @abstractmethod
    async def __aexit__(self, *args): ...

    @abstractmethod
    async def commit(self): ...

    @abstractmethod
    async def rollback(self): ...


class UnitOfWork(IUnitOfWork):
    """Реализация Unit of Work на базе SQLAlchemy AsyncSession."""

    def __init__(self):
        self.session_factory = async_session_maker

    async def __aenter__(self):
        # При входе в контекстный менеджер создается единая сессия для всех репозиториев
        self.session = self.session_factory()
        self.users = UserRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self):
        """Фиксация всех изменений транзакции."""
        await self.session.commit()

    async def rollback(self):
        """Откат транзакции при возникновении ошибки."""
        await self.session.rollback()
