"""Репозиторий для работы с командами (Team)."""

import uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from models.event import EventRegistration
from models.team import Team
from utils.repository import SQLAlchemyRepository


class TeamRepository(SQLAlchemyRepository):
    """Репозиторий таблицы команд."""

    model = Team

    async def get_by_id_for_update(self, team_id: uuid.UUID) -> Optional[Team]:
        """Получить команду по ID с пессимистичной блокировкой (SELECT FOR UPDATE).

        Используется для предотвращения Race Condition при одновременном вступлении участников.
        """
        stmt = select(self.model).where(self.model.id == team_id).with_for_update()
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id_with_members(self, team_id: uuid.UUID) -> Optional[Team]:
        """Получить команду по ID с жадной предзагрузкой капитана и участников с их профилями."""
        stmt = (
            select(self.model)
            .options(
                joinedload(self.model.captain),
                selectinload(self.model.members).joinedload(EventRegistration.user),
            )
            .where(self.model.id == team_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_event_id(
        self,
        event_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Team]:
        """Получить список всех команд мероприятия с предзагрузкой участников для каталога."""
        stmt = (
            select(self.model)
            .options(
                joinedload(self.model.captain),
                selectinload(self.model.members).joinedload(EventRegistration.user),
            )
            .where(self.model.event_id == event_id)
            .order_by(self.model.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_by_event(self, event_id: uuid.UUID) -> int:
        """Подсчёт команд мероприятия для пагинации."""
        stmt = select(func.count(self.model.id)).where(
            self.model.event_id == event_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def get_by_invite_token(self, invite_token: str) -> Optional[Team]:
        """Найти команду по секретному токену ссылки-приглашения (с предзагрузкой участников и события)."""
        stmt = (
            select(self.model)
            .options(
                joinedload(self.model.captain),
                joinedload(self.model.event),
                selectinload(self.model.members).joinedload(EventRegistration.user),
            )
            .where(self.model.invite_token == invite_token)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_invite_token_for_update(
        self, invite_token: str
    ) -> Optional[Team]:
        """Найти команду по секретному токену с пессимистичной блокировкой (SELECT FOR UPDATE)."""
        stmt = (
            select(self.model)
            .where(self.model.invite_token == invite_token)
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_members_count(self, team_id: uuid.UUID) -> int:
        """Получить текущее количество подтвержденных участников в команде."""
        stmt = select(func.count(EventRegistration.id)).where(
            EventRegistration.team_id == team_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def is_name_taken(
        self,
        event_id: uuid.UUID,
        name: str,
        exclude_team_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Проверить, занято ли название команды в рамках мероприятия (без учета регистра)."""
        clean_name = name.strip().lower()
        stmt = select(func.count(self.model.id)).where(
            self.model.event_id == event_id,
            func.lower(self.model.name) == clean_name,
        )
        if exclude_team_id is not None:
            stmt = stmt.where(self.model.id != exclude_team_id)

        res = await self.session.execute(stmt)
        return (res.scalar_one() or 0) > 0

    async def get_incomplete_teams_for_matching(
        self, event_id: uuid.UUID
    ) -> List[Team]:
        """Получить неполные команды хакатона с флагом allow_auto_match=True для умного матчинга."""
        stmt = (
            select(self.model)
            .options(selectinload(self.model.members).joinedload(EventRegistration.user))
            .where(
                self.model.event_id == event_id,
                self.model.allow_auto_match.is_(True),
            )
            .order_by(self.model.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
