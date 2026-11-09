"""Роутер мероприятий и каталога на главной странице."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import event_service
from auth.auth import current_user, fastapi_users
from models.enums import EventStatus
from models.user import User
from schemas.common import PaginatedResponse
from schemas.event import (
    EventDetailRead,
    EventRead,
    EventRegistrationCreate,
    EventRegistrationRead,
    SoloParticipantRead,
)
from services.event_services import EventServices

router = APIRouter(
    prefix="/events",
    tags=["Events"],
)

# Опциональная аутентификация: current_user_or_none будет None для анонимных запросов
current_user_or_none = fastapi_users.current_user(active=True, optional=True)


# ------------------------------------------------------------------
# GET /events — каталог публичных мероприятий на главной
# ------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedResponse[EventRead],
    summary="Каталог публичных мероприятий на главной странице",
)
async def get_events_catalog(
    is_featured: Optional[bool] = Query(
        default=None,
        description="Фильтр для верхнего слайдера (баннеры на главной)",
    ),
    status: Optional[EventStatus] = Query(
        default=None,
        description="Фильтр по статусу мероприятия",
    ),
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    size: int = Query(default=20, ge=1, le=100, description="Размер страницы"),
    limit: Optional[int] = Query(default=None, ge=1, le=100, description="Устаревший параметр лимита (совместимость)"),
    offset: Optional[int] = Query(default=None, ge=0, description="Устаревший параметр смещения (совместимость)"),
    service: EventServices = Depends(event_service),
):
    """Возвращает пагинированный список публичных мероприятий для главной страницы с фильтрацией."""
    if limit is not None:
        size = limit
        if offset is not None:
            page = (offset // limit) + 1

    return await service.get_public_events(
        is_featured=is_featured,
        status=status,
        page=page,
        size=size,
    )


# ------------------------------------------------------------------
# GET /events/{event_id_or_invite_code} — детальная страница
# ------------------------------------------------------------------


@router.get(
    "/{event_id_or_invite_code}",
    response_model=EventDetailRead,
    summary="Детальная страница мероприятия",
)
async def get_event_detail(
    event_id_or_invite_code: str,
    user: Optional[User] = Depends(current_user_or_none),
    service: EventServices = Depends(event_service),
):
    """Возвращает полную информацию о мероприятии.

    Для авторизованного пользователя также включает поле my_registration
    (зарегистрирован ли он и в какой команде состоит).
    """
    current_user_id = user.id if user else None
    result = await service.get_event_detail(
        identifier=event_id_or_invite_code,
        current_user_id=current_user_id,
    )

    # Собираем ответ в формате EventDetailRead
    event = result["event"]
    return EventDetailRead.model_validate(
        event,
        from_attributes=True,
    ).model_copy(
        update={
            "my_registration": result["my_registration"],
        }
    )


# ------------------------------------------------------------------
# POST /events/{event_id}/register — регистрация участника
# ------------------------------------------------------------------


@router.post(
    "/{event_id}/register",
    response_model=EventRegistrationRead,
    summary="Регистрация участника на мероприятие",
)
async def register_for_event(
    event_id: uuid.UUID,
    registration_data: EventRegistrationCreate,
    user: User = Depends(current_user),
    service: EventServices = Depends(event_service),
):
    """Регистрирует текущего пользователя на мероприятие.

    Сохраняет и валидирует ответы на вопросы анкеты мероприятия (custom_answers).
    """
    return await service.register_for_event(
        event_id=event_id,
        user_id=user.id,
        registration_data=registration_data,
    )


# ------------------------------------------------------------------
# GET /events/{event_id}/solo-participants — каталог одиночек
# ------------------------------------------------------------------


@router.get(
    "/{event_id}/solo-participants",
    response_model=PaginatedResponse[SoloParticipantRead],
    summary="Каталог свободных участников без команды",
)
async def get_solo_participants(
    event_id: uuid.UUID,
    specialization: Optional[str] = Query(
        default=None,
        description="Фильтр по специализации (например: frontend, backend)",
    ),
    skills: Optional[List[str]] = Query(
        default=None,
        description="Фильтр по списку навыков (стек: React, Docker)",
    ),
    tags: Optional[List[str]] = Query(
        default=None,
        description="Универсальный фильтр по тегам (роли и навыки)",
    ),
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    size: int = Query(default=20, ge=1, le=100, description="Размер страницы"),
    limit: Optional[int] = Query(default=None, ge=1, le=100, description="Устаревший параметр лимита (совместимость)"),
    offset: Optional[int] = Query(default=None, ge=0, description="Устаревший параметр смещения (совместимость)"),
    user: User = Depends(current_user),
    service: EventServices = Depends(event_service),
):
    """Возвращает пагинированный список свободных участников мероприятия (team_id IS NULL).

    Используется на экране «Пригласить участников в команду».
    """
    if limit is not None:
        size = limit
        if offset is not None:
            page = (offset // limit) + 1

    # Объединяем фильтры для гибкого поиска
    search_tags: List[str] = []
    if specialization:
        search_tags.append(specialization)
    if skills:
        search_tags.extend(skills)
    if tags:
        search_tags.extend(tags)

    filter_tags = list(set(search_tags)) if search_tags else None

    return await service.get_solo_participants(
        event_id=event_id,
        tags=filter_tags,
        page=page,
        size=size,
    )
