from abc import ABC, abstractmethod
from typing import Any
from sqlalchemy import insert, select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession


class AbstractRepository(ABC):

    @abstractmethod
    async def add_one(self, data: dict) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def find_all(self, **filter_by) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    async def find_one_or_none(self, **filter_by) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    async def find_filter(self, *filters) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    async def update(self, id: Any, values: dict) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def delete_one(self, id: Any) -> Any:
        raise NotImplementedError


class SQLAlchemyRepository(AbstractRepository):
    model = None

    def __init__(self, session: AsyncSession):
        # Используем ТОЛЬКО эту общую сессию от UnitOfWork во всех методах!
        self.session = session

    async def add_one(self, data: dict):
        stmt = (
            insert(self.model)
            .values(**data)
            .returning(self.model)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one()

    async def find_all(self, **filter_by):
        # Работает и без аргументов find_all(), и с именными фильтрами find_all(course=1)
        stmt = select(self.model).filter_by(**filter_by)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def find_one_or_none(self, **filter_by):
        stmt = select(self.model).filter_by(**filter_by)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_filter(self, *filters):
        # Для сложных условий (>, <, in_): find_filter(User.course >= 2)
        stmt = select(self.model).where(*filters)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update(self, id: Any, values: dict):
        stmt = (
            update(self.model)
            .where(self.model.id == id)
            .values(**values)
            .returning(self.model)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_one(self, id: Any):
        stmt = (
            delete(self.model)
            .where(self.model.id == id)
            .returning(self.model.id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()