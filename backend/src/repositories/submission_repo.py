"""Репозиторий для работы со сданными проектами (Submission)."""

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from models.submission import Submission
from models.team import Team
from utils.repository import SQLAlchemyRepository


class SubmissionRepository(SQLAlchemyRepository):
    """Репозиторий таблицы submissions."""

    model = Submission

    async def get_by_team_id(self, team_id: uuid.UUID) -> Optional[Submission]:
        """Получить решение команды по ID команды."""
        stmt = (
            select(self.model)
            .options(
                joinedload(self.model.submitted_by_user),
                joinedload(self.model.team),
            )
            .where(self.model.team_id == team_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_event_id(self, event_id: uuid.UUID) -> List[Submission]:
        """Получить все сданные решения хакатона с предзагрузкой команд и авторов сабмита."""
        stmt = (
            select(self.model)
            .options(
                joinedload(self.model.submitted_by_user),
                joinedload(self.model.team).joinedload(Team.captain),
            )
            .where(self.model.event_id == event_id)
            .order_by(self.model.submitted_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
