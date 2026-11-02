"""Роутер для работы с профилями пользователей."""

import uuid
from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import event_service, user_service
from auth.auth import current_user
from auth.schemas import UserPasswordChange, UserRead, UserUpdate
from models.user import User
from schemas.event import UserEventItemRead
from services.event_services import EventServices
from services.user_services import UserServices

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Получить профиль текущего пользователя",
)
async def get_current_user_profile(
    user: User = Depends(current_user),
    service: UserServices = Depends(user_service),
):
    """Возвращает полную информацию о профиле авторизованного пользователя."""
    return await service.get_user_by_id(user.id)


@router.patch(
    "/me",
    response_model=UserRead,
    summary="Обновить профиль текущего пользователя",
)
async def update_current_user_profile(
    user_data: UserUpdate,
    user: User = Depends(current_user),
    service: UserServices = Depends(user_service),
):
    """Обновляет поля профиля (ФИО, вуз, навыки, соцсети, о себе)."""
    return await service.update_profile(user.id, user_data)


@router.post(
    "/me/change-password",
    summary="Сменить пароль текущего пользователя",
)
async def change_current_user_password(
    password_data: UserPasswordChange,
    user: User = Depends(current_user),
    service: UserServices = Depends(user_service),
):
    """Безопасная смена пароля с обязательным подтверждением старого пароля."""
    await service.change_password(user.id, password_data)
    return {"detail": "Пароль успешно изменен"}


@router.post(
    "/me/telegram-bind-link",
    summary="Сгенерировать ссылку для привязки Telegram-бота",
)
async def create_telegram_bind_link(
    user: User = Depends(current_user),
    service: UserServices = Depends(user_service),
):
    """Генерирует секретную deep-link ссылку для привязки аккаунта в Telegram."""
    link = await service.generate_telegram_bind_link(user.id)
    return {"bind_url": link}


@router.get(
    "/me/events",
    response_model=List[UserEventItemRead],
    summary="Список мероприятий текущего пользователя",
)
async def get_my_events(
    user: User = Depends(current_user),
    service: EventServices = Depends(event_service),
):
    """Возвращает мероприятия, на которые зарегистрирован текущий пользователь.

    Используется для блока «Ваши события» в профиле и виджета на главной.
    """
    registrations = await service.get_user_events(user_id=user.id)
    return [
        UserEventItemRead(
            event=reg.event,
            registration=reg,
        )
        for reg in registrations
    ]


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Получить публичный профиль пользователя по ID",
)
async def get_user_by_id(
    user_id: uuid.UUID,
    user: User = Depends(current_user),
    service: UserServices = Depends(user_service),
):
    """Возвращает информацию о профиле любого участника (для просмотра карточки кандидата)."""
    return await service.get_user_by_id(user_id)
