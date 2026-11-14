"""Роутер заявок и приглашений в команды."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Request

from api.dependencies import team_service
from auth.auth import current_user
from models.user import User
from schemas.team import (
    TeamApplicationCreate,
    TeamInviteCreate,
    TeamRequestRead,
)
from services.team_services import TeamServices
from utils.limiter import limiter

router = APIRouter(tags=["Team Requests"])


@router.get(
    "/events/{event_id}/my-requests",
    response_model=List[TeamRequestRead],
    summary="Получить мои заявки и приглашения",
)
async def get_my_requests(
    event_id: uuid.UUID,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    return await service.get_my_requests(event_id=event_id, user_id=user.id)


@router.post(
    "/teams/{team_id}/apply",
    response_model=TeamRequestRead,
    summary="Откликнуться на команду",
)
@limiter.limit("20/minute")
async def apply_to_team(
    request: Request,
    team_id: uuid.UUID,
    user: User = Depends(current_user),
    data: Optional[TeamApplicationCreate] = Body(default=None),
    service: TeamServices = Depends(team_service),
):
    return await service.apply_to_team(team_id=team_id, user_id=user.id, data=data)


@router.post(
    "/teams/{team_id}/invite/{user_id}",
    response_model=TeamRequestRead,
    summary="Пригласить участника в команду",
)
@limiter.limit("20/minute")
async def invite_user_to_team(
    request: Request,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(current_user),
    data: Optional[TeamInviteCreate] = Body(default=None),
    service: TeamServices = Depends(team_service),
):
    return await service.invite_user_to_team(
        team_id=team_id,
        captain_id=user.id,
        target_user_id=user_id,
        data=data,
    )


@router.post(
    "/team-requests/{request_id}/captain-approve",
    response_model=TeamRequestRead,
    summary="Одобрить заявку капитаном",
)
async def captain_approve_request(
    request_id: uuid.UUID,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    return await service.captain_approve_request(request_id=request_id, captain_id=user.id)


@router.post(
    "/team-requests/{request_id}/user-confirm",
    response_model=TeamRequestRead,
    summary="Подтвердить заявку участником",
)
async def user_confirm_request(
    request_id: uuid.UUID,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    return await service.user_confirm_request(request_id=request_id, user_id=user.id)


@router.post(
    "/team-requests/{request_id}/reject",
    response_model=TeamRequestRead,
    summary="Отклонить или отменить заявку",
)
async def reject_request(
    request_id: uuid.UUID,
    user: User = Depends(current_user),
    service: TeamServices = Depends(team_service),
):
    return await service.reject_request(request_id=request_id, actor_user_id=user.id)
