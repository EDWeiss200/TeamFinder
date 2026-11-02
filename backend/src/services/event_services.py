"""Сервисный слой для работы с мероприятиями и регистрациями участников."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from models.enums import EventStatus
from models.event import Event, EventRegistration
from schemas.event import EventRegistrationCreate
from utils.exceptions import (
    EntityNotFoundError,
    InvalidStateError,
)
from utils.uow import IUnitOfWork


class EventServices:
    """Сервис управления мероприятиями, регистрациями и каталогом участников."""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------
    # Каталог мероприятий (главная страница)
    # ------------------------------------------------------------------

    async def get_public_events(
        self,
        is_featured: Optional[bool] = None,
        status: Optional[EventStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Event]:
        """Получить список публичных мероприятий для главной страницы."""
        async with self.uow:
            return await self.uow.events.get_public_events(
                is_featured=is_featured,
                status=status,
                limit=limit,
                offset=offset,
            )

    # ------------------------------------------------------------------
    # Детальная страница мероприятия
    # ------------------------------------------------------------------

    async def get_event_detail(
        self,
        identifier: str,
        current_user_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """Получить детальную информацию о мероприятии.

        Возвращает словарь с данными мероприятия и опциональной
        регистрацией текущего пользователя (my_registration).
        """
        async with self.uow:
            event = await self.uow.events.get_by_id_or_invite_code(identifier)
            if not event:
                raise EntityNotFoundError(f"Мероприятие '{identifier}' не найдено")

            my_registration = None
            if current_user_id is not None:
                my_registration = await self.uow.registrations.get_by_event_and_user(
                    event_id=event.id,
                    user_id=current_user_id,
                )

            return {
                "event": event,
                "my_registration": my_registration,
            }

    # ------------------------------------------------------------------
    # Регистрация участника на мероприятие
    # ------------------------------------------------------------------

    async def register_for_event(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        registration_data: EventRegistrationCreate,
    ) -> EventRegistration:
        """Зарегистрировать участника на мероприятие.

        Проверяет:
        1. Существование мероприятия и статус REGISTRATION.
        2. Что пользователь еще не зарегистрирован на этот хакатон.
        """
        async with self.uow:
            # Проверяем существование мероприятия
            event = await self.uow.events.find_one_or_none(id=event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {event_id} не найдено")

            # Проверяем, что регистрация открыта
            if event.status != EventStatus.REGISTRATION:
                raise InvalidStateError(
                    "Регистрация на это мероприятие закрыта "
                    f"(текущий статус: {event.status.value})"
                )

            # Проверяем дедлайн регистрации
            now = datetime.now(timezone.utc)
            if now > event.registration_end:
                raise InvalidStateError("Срок регистрации на мероприятие истек")

            # Проверяем, что пользователь ещё не зарегистрирован
            existing = await self.uow.registrations.get_by_event_and_user(
                event_id=event_id,
                user_id=user_id,
            )
            if existing:
                raise InvalidStateError("Вы уже зарегистрированы на это мероприятие")

            # Создаём регистрацию через базовый add_one
            registration = await self.uow.registrations.add_one(
                {
                    "event_id": event_id,
                    "user_id": user_id,
                    "custom_answers": registration_data.custom_answers,
                }
            )
            await self.uow.commit()
            return registration

    # ------------------------------------------------------------------
    # Каталог свободных участников (одиночки)
    # ------------------------------------------------------------------

    async def get_solo_participants(
        self,
        event_id: uuid.UUID,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[EventRegistration]:
        """Получить каталог свободных участников без команды на мероприятии."""
        async with self.uow:
            # Проверяем существование мероприятия
            event = await self.uow.events.find_one_or_none(id=event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {event_id} не найдено")

            return await self.uow.registrations.get_solo_participants(
                event_id=event_id,
                tags=tags,
                limit=limit,
                offset=offset,
            )

    # ------------------------------------------------------------------
    # Мероприятия текущего пользователя
    # ------------------------------------------------------------------

    async def get_user_events(
        self,
        user_id: uuid.UUID,
    ) -> List[EventRegistration]:
        """Получить список мероприятий, на которые зарегистрирован пользователь."""
        async with self.uow:
            return await self.uow.registrations.get_user_registrations(
                user_id=user_id,
            )
