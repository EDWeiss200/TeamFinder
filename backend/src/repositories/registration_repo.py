"""Репозиторий для работы с регистрациями участников на мероприятия (EventRegistration)."""

import uuid
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from models.event import EventRegistration
from models.user import User
from utils.repository import SQLAlchemyRepository


class EventRegistrationRepository(SQLAlchemyRepository):
    """Репозиторий таблицы регистраций участников на мероприятия."""

    model = EventRegistration

    async def get_solo_participants(
        self,
        event_id: uuid.UUID,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[EventRegistration]:
        """Получить свободных участников мероприятия без команды (team_id IS NULL).

        Выполняет JOIN с пользователями, жадную предзагрузку связанных данных профиля (joinedload)
        и фильтрацию по массиву тегов пользователя (User.skills.overlap).

        :param event_id: ID мероприятия
        :param tags: список тегов для проверки пересечения с навыками и компетенциями
        :param limit: лимит записей (пагинация)
        :param offset: смещение (пагинация)
        """
        stmt = (
            select(self.model)
            .options(joinedload(self.model.user))
            .join(User, self.model.user_id == User.id)
            .where(
                self.model.event_id == event_id,
                self.model.team_id.is_(None),
            )
        )

        if tags:
            stmt = stmt.where(
                or_(
                    User.specializations.overlap(tags),
                    User.skills.overlap(tags),
                )
            )

        stmt = stmt.order_by(self.model.registered_at.asc()).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_solo_participants(
        self,
        event_id: uuid.UUID,
        tags: Optional[List[str]] = None,
    ) -> int:
        """Подсчет общего количества свободных участников с учетом тегов."""
        stmt = (
            select(func.count(self.model.id))
            .join(User, self.model.user_id == User.id)
            .where(
                self.model.event_id == event_id,
                self.model.team_id.is_(None),
            )
        )

        if tags:
            stmt = stmt.where(
                or_(
                    User.specializations.overlap(tags),
                    User.skills.overlap(tags),
                )
            )

        res = await self.session.execute(stmt)
        return res.scalar_one() or 0


    async def get_by_event_and_user_for_update(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[EventRegistration]:
        """Найти регистрацию с пессимистичной блокировкой (SELECT FOR UPDATE) для защиты от Race Condition."""
        stmt = (
            select(self.model)
            .where(
                self.model.event_id == event_id,
                self.model.user_id == user_id,
            )
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_event_and_user(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[EventRegistration]:
        """Найти регистрацию пользователя на мероприятии с предзагрузкой команды и профиля."""
        stmt = (
            select(self.model)
            .options(
                joinedload(self.model.user),
                joinedload(self.model.team),
            )
            .where(
                self.model.event_id == event_id,
                self.model.user_id == user_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_user_registrations(
        self,
        user_id: uuid.UUID,
    ) -> List[EventRegistration]:
        """Получить все регистрации пользователя с предзагрузкой мероприятий и команд (для профиля)."""
        stmt = (
            select(self.model)
            .options(
                joinedload(self.model.event),
                joinedload(self.model.team),
            )
            .where(self.model.user_id == user_id)
            .order_by(self.model.registered_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
