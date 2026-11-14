"""Сервисный слой для работы с мероприятиями и регистрациями участников."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.enums import EventStatus
from models.event import Event, EventRegistration
from schemas.common import PaginatedResponse
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
    # Ленивая смена статусов хакатона (Lazy Transitions)
    # ------------------------------------------------------------------

    async def _apply_lazy_status_transitions(self, event: Event) -> None:
        """Автоматический перевод этапа хакатона при наступлении дедлайнов.

        1. REGISTRATION -> TEAM_LOCK (по истечении registration_end) с отменой висящих заявок.
        2. SUBMISSION -> FINISHED (по истечении submission_deadline).
        """
        now = datetime.now(timezone.utc)
        status_changed = False

        if event.status == EventStatus.REGISTRATION and now > event.registration_end:
            event.status = EventStatus.TEAM_LOCK
            await self.uow.events.update(event.id, {"status": EventStatus.TEAM_LOCK})
            # Автоматическая отмена всех незавершенных заявок и инвайтов
            await self.uow.requests.cancel_all_event_pending_requests(event.id)
            status_changed = True

        elif event.status == EventStatus.SUBMISSION and now > event.submission_deadline:
            event.status = EventStatus.FINISHED
            await self.uow.events.update(event.id, {"status": EventStatus.FINISHED})
            status_changed = True

        if status_changed:
            await self.uow.commit()

    # ------------------------------------------------------------------
    # Валидация кастомных полей анкеты
    # ------------------------------------------------------------------

    def _validate_custom_answers(
        self,
        schema: Optional[Any],
        answers: Optional[Dict[str, Any]],
    ) -> None:
        """Проверяет соответствие ответов участника схеме анкеты хакатона."""
        if not schema:
            return

        answers_dict = answers or {}
        # Схема может быть списком словарей полей
        fields_list = schema if isinstance(schema, list) else schema.get("fields", [])

        for field in fields_list:
            if not isinstance(field, dict):
                continue

            field_id = field.get("id")
            field_label = field.get("label", field_id)
            is_required = field.get("required", False)
            field_type = field.get("type", "text")
            options = field.get("options", [])

            value = answers_dict.get(field_id)

            # Проверка обязательности поля
            if is_required and (
                value is None or (isinstance(value, str) and not value.strip())
            ):
                raise InvalidStateError(
                    f"Обязательное поле анкеты '{field_label}' не заполнено"
                )

            # Проверка допустимых опций для select
            if value is not None and field_type == "select" and options:
                if value not in options:
                    raise InvalidStateError(
                        f"Недопустимое значение для поля '{field_label}'. "
                        f"Допустимые варианты: {', '.join(map(str, options))}"
                    )

    # ------------------------------------------------------------------
    # Каталог мероприятий (главная страница)
    # ------------------------------------------------------------------

    async def get_public_events(
        self,
        is_featured: Optional[bool] = None,
        status: Optional[EventStatus] = None,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse[Event]:
        """Получить список публичных мероприятий с пагинацией и проверкой дедлайнов."""
        offset = (page - 1) * size
        async with self.uow:
            events = await self.uow.events.get_public_events(
                is_featured=is_featured,
                status=status,
                limit=size,
                offset=offset,
            )
            # Применяем ленивые переходы для отображаемых событий
            for ev in events:
                await self._apply_lazy_status_transitions(ev)

            total = await self.uow.events.count_public_events(
                is_featured=is_featured,
                status=status,
            )
            return PaginatedResponse.create(
                items=events,
                total=total,
                page=page,
                size=size,
            )

    # ------------------------------------------------------------------
    # Детальная страница мероприятия
    # ------------------------------------------------------------------

    async def get_event_detail(
        self,
        identifier: str,
        current_user_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """Получить детальную информацию о мероприятии."""
        async with self.uow:
            event = await self.uow.events.get_by_id_or_invite_code(identifier)
            if not event:
                raise EntityNotFoundError(f"Мероприятие '{identifier}' не найдено")

            await self._apply_lazy_status_transitions(event)

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
        """Зарегистрировать участника на мероприятие."""
        async with self.uow:
            event = await self.uow.events.find_one_or_none(id=event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {event_id} не найдено")

            # Проверяем и применяем переход дедлайна
            await self._apply_lazy_status_transitions(event)

            if event.status != EventStatus.REGISTRATION:
                raise InvalidStateError(
                    "Регистрация на это мероприятие закрыта "
                    f"(текущий статус: {event.status.value})"
                )

            now = datetime.now(timezone.utc)
            if now > event.registration_end:
                raise InvalidStateError("Срок регистрации на мероприятие истек")

            # Валидируем кастомные ответы анкеты хакатона
            self._validate_custom_answers(
                event.custom_fields_schema,
                registration_data.custom_answers,
            )

            # Проверяем, что пользователь ещё не зарегистрирован
            existing = await self.uow.registrations.get_by_event_and_user(
                event_id=event_id,
                user_id=user_id,
            )
            if existing:
                raise InvalidStateError("Вы уже зарегистрированы на это мероприятие")

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
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse[EventRegistration]:
        """Получить каталог свободных участников без команды с пагинацией."""
        offset = (page - 1) * size
        async with self.uow:
            event = await self.uow.events.find_one_or_none(id=event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {event_id} не найдено")

            await self._apply_lazy_status_transitions(event)

            items = await self.uow.registrations.get_solo_participants(
                event_id=event_id,
                tags=tags,
                limit=size,
                offset=offset,
            )
            total = await self.uow.registrations.count_solo_participants(
                event_id=event_id,
                tags=tags,
            )
            return PaginatedResponse.create(
                items=items,
                total=total,
                page=page,
                size=size,
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
