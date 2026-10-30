"""Репозиторий для работы с мероприятиями (Event)."""

import uuid
from typing import List, Optional, Union

from sqlalchemy import select

from models.enums import EventStatus
from models.event import Event
from utils.repository import SQLAlchemyRepository


class EventRepository(SQLAlchemyRepository):
    """Репозиторий таблицы мероприятий."""

    model = Event

    async def get_by_id_or_invite_code(
        self,
        identifier: Union[str, uuid.UUID],
    ) -> Optional[Event]:
        """Поиск мероприятия по UUID или по инвайт-коду.

        Сначала пытается обработать идентификатор как UUID через базовый find_one_or_none(id=...),
        а если строка не является UUID или запись не найдена — ищет по invite_code.
        """
        if isinstance(identifier, uuid.UUID):
            return await self.find_one_or_none(id=identifier)

        try:
            parsed_uuid = uuid.UUID(identifier)
            event = await self.find_one_or_none(id=parsed_uuid)
            if event is not None:
                return event
        except (ValueError, AttributeError):
            pass

        return await self.find_one_or_none(invite_code=str(identifier))

    async def get_public_events(
        self,
        is_featured: Optional[bool] = None,
        status: Optional[EventStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Event]:
        """Получение списка публичных мероприятий для главной страницы с сортировкой и пагинацией.

        :param is_featured: фильтр для карточек верхнего слайдера
        :param status: фильтр по статусу жизненного цикла (например, REGISTRATION)
        :param limit: количество записей (пагинация)
        :param offset: смещение (пагинация)
        """
        stmt = select(self.model).where(self.model.is_public.is_(True))

        if is_featured is not None:
            stmt = stmt.where(self.model.is_featured == is_featured)

        if status is not None:
            stmt = stmt.where(self.model.status == status)

        stmt = stmt.order_by(self.model.event_start.asc()).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
