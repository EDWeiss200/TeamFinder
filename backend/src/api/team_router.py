"""Роутер управления командами мероприятия."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import team_service
from auth.auth import current_user, fastapi_users
from models.enums import ParticipantSpecialization
from models.user import User
from schemas.common import PaginatedResponse
from schemas.team import TeamCreate, TeamDetailRead, TeamRead, TeamUpdate
from services.team_services import TeamServices

router = APIRouter(tags=["Teams"])

current_user_or_none = fastapi_users.current_user(active=True, optional=True)


@router.get(
    "/events/{event_id}/teams",
    response_model=PaginatedResponse[TeamRead],
    summary="Получить список команд мероприятия",
)
async def get_event_teams(
    event_id: uuid.UUID,
    needed_role: Optional[ParticipantSpecialization] = Query(
        default=None,
        description="Фильтр по специализации, которую команда ищет",
    ),
    has_free_slots: Optional[bool] = Query(
        default=None,
        description="Фильтр только по командам со свободными местами",
    ),
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    size: int = Query(default=20, ge=1, le=100, description="Размер страницы"),
    service: TeamServices = Depends(team_service),
):
    """Вернуть каталог команд конкретного мероприятия."""
    return await service.get_event_teams(
        event_id=event_id,
        needed_role=needed_role,
        has_free_slots=has_free_slots,
        page=page,
        size=size,
    )


@router.post(
    "/events/{event_id}/teams",
    response_model=TeamDetailRead,
    summary="Создать новую команду на мероприятии",
)
async def create_team(
    event_id: uuid.UUID,
    team_data: TeamCreate,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    """Создать команду и вернуть её детальные данные для капитана."""
    team = await service.create_team(
        event_id=event_id,
        creator_id=user.id,
        team_data=team_data,
    )
    return await service.get_team_detail(team.id, user)


@router.get(
    "/teams/{team_id}",
    response_model=TeamDetailRead,
    summary="Получить детальную информацию о команде",
)
async def get_team_detail(
    team_id: uuid.UUID,
    user: Optional[User] = Depends(current_user_or_none),
    service: TeamServices = Depends(team_service),
):
    """Вернуть карточку команды с безопасной маскировкой invite_token."""
    return await service.get_team_detail(team_id=team_id, current_user=user)


@router.patch(
    "/teams/{team_id}",
    response_model=TeamDetailRead,
    summary="Обновить данные команды",
)
async def update_team(
    team_id: uuid.UUID,
    update_data: TeamUpdate,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    """Изменить данные команды и вернуть обновлённую карточку."""
    await service.update_team(
        team_id=team_id,
        actor_user=user,
        update_data=update_data,
    )
    return await service.get_team_detail(team_id=team_id, current_user=user)


@router.post(
    "/teams/{team_id}/regenerate-token",
    summary="Перевыпустить invite_token команды",
)
async def regenerate_invite_token(
    team_id: uuid.UUID,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    """Перевыпустить секретный invite_token капитаном."""
    token = await service.regenerate_invite_token(
        team_id=team_id,
        actor_user_id=user.id,
    )
    return {"invite_token": token}


@router.post(
    "/teams/join-by-token/{invite_token}",
    response_model=TeamDetailRead,
    summary="Вступить в команду по invite_token",
)
async def join_by_invite_token(
    invite_token: str,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    """Добавить пользователя в команду по секретной ссылке."""
    team = await service.join_by_invite_token(
        invite_token=invite_token, user_id=user.id
    )
    return await service.get_team_detail(team_id=team.id, current_user=user)


@router.post(
    "/teams/{team_id}/leave",
    response_model=Optional[TeamDetailRead],
    summary="Выйти из команды",
)
async def leave_team(
    team_id: uuid.UUID,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    """Выйти из команды. Если команда опустела и была удалена, вернётся null."""
    team = await service.leave_team(team_id=team_id, user_id=user.id)
    if team is None:
        return None
    return await service.get_team_detail(team_id=team.id, current_user=user)


@router.delete(
    "/teams/{team_id}/members/{user_id}",
    response_model=Optional[TeamDetailRead],
    summary="Исключить участника из команды",
)
async def kick_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    """Исключить участника из команды капитаном."""
    team = await service.kick_member(
        team_id=team_id,
        actor_user_id=user.id,
        member_user_id=user_id,
    )
    if team is None:
        return None
    return await service.get_team_detail(team_id=team.id, current_user=user)
