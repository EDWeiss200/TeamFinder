"""Репозиторий для работы с пользователями."""

from typing import Optional
from sqlalchemy import select
from utils.repository import SQLAlchemyRepository
from models.user import User


class UserRepository(SQLAlchemyRepository):
    """Репозиторий таблицы пользователей."""

    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Поиск пользователя по Telegram ID."""
        stmt = select(self.model).where(self.model.telegram_id == telegram_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_bind_token(self, token: str) -> Optional[User]:
        """Поиск пользователя по токену привязки Telegram-бота."""
        stmt = select(self.model).where(self.model.telegram_bind_token == token)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
