"""Репозиторий для работы с заявками и приглашениями в команды (TeamRequest)."""

import uuid
from typing import List, Optional

from sqlalchemy import select, update

from models.enums import TeamRequestStatus
from models.team import TeamRequest
from utils.repository import SQLAlchemyRepository


class RequestRepository(SQLAlchemyRepository):
    """Репозиторий таблицы team_requests."""

    model = TeamRequest

    async def get_active_request(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[TeamRequest]:
        """Найти активную заявку или приглашение между командой и пользователем."""
        active_statuses = [
            TeamRequestStatus.PENDING_CAPTAIN,
            TeamRequestStatus.PENDING_USER,
        ]
        stmt = select(self.model).where(
            self.model.team_id == team_id,
            self.model.user_id == user_id,
            self.model.status.in_(active_statuses),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def cancel_other_user_requests(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        exclude_request_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Массово перевести все остальные активные заявки пользователя на событии в статус CANCELLED."""
        active_statuses = [
            TeamRequestStatus.PENDING_CAPTAIN,
            TeamRequestStatus.PENDING_USER,
        ]
        stmt = (
            update(self.model)
            .where(
                self.model.event_id == event_id,
                self.model.user_id == user_id,
                self.model.status.in_(active_statuses),
            )
            .values(status=TeamRequestStatus.CANCELLED)
        )
        if exclude_request_id is not None:
            stmt = stmt.where(self.model.id != exclude_request_id)

        await self.session.execute(stmt)

    async def cancel_team_pending_requests(
        self,
        team_id: uuid.UUID,
        exclude_request_id: Optional[uuid.UUID] = None,
    ) -> List[TeamRequest]:
        """Аннулировать все висящие заявки и офферы команды при ее заполнении (защита от овербукинга)."""
        active_statuses = [
            TeamRequestStatus.PENDING_CAPTAIN,
            TeamRequestStatus.PENDING_USER,
        ]
        # Сначала получаем заявки, чтобы иметь возможность отправить уведомления
        stmt_select = select(self.model).where(
            self.model.team_id == team_id,
            self.model.status.in_(active_statuses),
        )
        if exclude_request_id is not None:
            stmt_select = stmt_select.where(self.model.id != exclude_request_id)

        res = await self.session.execute(stmt_select)
        requests_to_cancel = list(res.scalars().all())

        if requests_to_cancel:
            cancel_ids = [r.id for r in requests_to_cancel]
            stmt_update = (
                update(self.model)
                .where(self.model.id.in_(cancel_ids))
                .values(status=TeamRequestStatus.CANCELLED)
            )
            await self.session.execute(stmt_update)

        return requests_to_cancel

    async def cancel_all_event_pending_requests(self, event_id: uuid.UUID) -> None:
        """Массово отменить все активные заявки хакатона при наступлении TEAM_LOCK."""
        active_statuses = [
            TeamRequestStatus.PENDING_CAPTAIN,
            TeamRequestStatus.PENDING_USER,
        ]
        stmt = (
            update(self.model)
            .where(
                self.model.event_id == event_id,
                self.model.status.in_(active_statuses),
            )
            .values(status=TeamRequestStatus.CANCELLED)
        )
        await self.session.execute(stmt)

    async def get_user_event_requests(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> List[TeamRequest]:
        """Получить все заявки пользователя в рамках мероприятия."""
        stmt = (
            select(self.model)
            .where(
                self.model.event_id == event_id,
                self.model.user_id == user_id,
            )
            .order_by(self.model.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_team_incoming_requests(
        self,
        team_id: uuid.UUID,
    ) -> List[TeamRequest]:
        """Получить все входящие и исходящие заявки команды."""
        stmt = (
            select(self.model)
            .where(self.model.team_id == team_id)
            .order_by(self.model.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
