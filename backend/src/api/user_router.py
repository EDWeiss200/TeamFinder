"""Роутер для работы с профилями пользователей."""

import uuid
from fastapi import APIRouter, Depends

from api.dependencies import user_service
from auth.auth import current_user
from auth.schemas import UserRead, UserUpdate
from models.user import User
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
