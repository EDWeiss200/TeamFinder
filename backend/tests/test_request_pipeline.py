import pytest
from unittest.mock import AsyncMock

from models.enums import ParticipantSpecialization, TeamRequestStatus, TeamRequestType
from schemas.team import TeamApplicationCreate, TeamInviteCreate
from services.team_services import TeamServices
from utils.exceptions import (
    AlreadyInTeamError,
    InvalidStateError,
    PermissionDeniedError,
    TeamIsFullError,
)

from tests.conftest import make_event, make_registration, make_team, make_team_request, make_user


def build_service(fake_uow):
    service = TeamServices(fake_uow)
    return service


@pytest.mark.asyncio
async def test_apply_to_team_creates_request(fake_uow):
    event = make_event()
    captain = make_user()
    user = make_user(specializations=[ParticipantSpecialization.BACKEND.value])
    team = make_team(event, captain, needed_roles=[ParticipantSpecialization.BACKEND.value])
    registration = make_registration(user, event)
    request = make_team_request(
        event,
        team,
        user,
        request_type=TeamRequestType.APPLICATION,
        status=TeamRequestStatus.PENDING_CAPTAIN,
    )

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.users.find_one_or_none.return_value = user
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = registration
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.teams.get_members_count.return_value = 1
    fake_uow.requests.get_active_request.return_value = None
    fake_uow.requests.add_one.return_value = request
    fake_uow.requests.get_by_id_with_relations.return_value = request

    service = build_service(fake_uow)
    data = TeamApplicationCreate(message="Хочу в команду", target_role=ParticipantSpecialization.BACKEND)
    result = await service.apply_to_team(team.id, user.id, data)

    assert result is request
    fake_uow.requests.add_one.assert_awaited_once()
    assert fake_uow.committed is True
    assert fake_uow.requests.cancel_other_user_requests.await_count == 0


@pytest.mark.asyncio
async def test_invite_user_to_team_creates_request(fake_uow):
    event = make_event()
    captain = make_user()
    user = make_user()
    team = make_team(event, captain, needed_roles=[ParticipantSpecialization.DESIGN.value])
    registration = make_registration(user, event)
    request = make_team_request(
        event,
        team,
        user,
        request_type=TeamRequestType.INVITE,
        status=TeamRequestStatus.PENDING_USER,
    )

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.users.find_one_or_none.return_value = user
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = registration
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.teams.get_members_count.return_value = 1
    fake_uow.requests.get_active_request.return_value = None
    fake_uow.requests.add_one.return_value = request
    fake_uow.requests.get_by_id_with_relations.return_value = request

    service = build_service(fake_uow)
    data = TeamInviteCreate(message="Приглашаю", target_role=ParticipantSpecialization.DESIGN)
    result = await service.invite_user_to_team(team.id, captain.id, user.id, data)

    assert result is request
    fake_uow.requests.add_one.assert_awaited_once()
    assert fake_uow.committed is True


@pytest.mark.asyncio
async def test_apply_to_team_anti_collision_accepts_pending_invite(fake_uow):
    event = make_event(max_team_size=3)
    captain = make_user()
    user = make_user(
        specializations=[ParticipantSpecialization.BACKEND.value],
    )
    team = make_team(
        event,
        captain,
        max_members=3,
        needed_roles=[ParticipantSpecialization.DESIGN.value, ParticipantSpecialization.BACKEND.value],
    )
    registration = make_registration(user, event)
    existing = make_team_request(
        event,
        team,
        user,
        target_role=ParticipantSpecialization.DESIGN.value,
        status=TeamRequestStatus.PENDING_USER,
        request_type=TeamRequestType.INVITE,
    )

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.users.find_one_or_none.return_value = user
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = registration
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.teams.get_members_count.return_value = 2
    fake_uow.requests.get_active_request.return_value = existing
    fake_uow.requests.get_by_id_with_relations.return_value = existing

    service = build_service(fake_uow)
    result = await service.apply_to_team(team.id, user.id)

    assert result.status == TeamRequestStatus.ACCEPTED
    assert registration.team_id == team.id
    assert fake_uow.requests.cancel_other_user_requests.await_count == 1
    fake_uow.requests.cancel_team_pending_requests.assert_awaited_once_with(
        team.id,
        exclude_request_id=existing.id,
    )
    assert team.needed_roles == [ParticipantSpecialization.BACKEND.value]


@pytest.mark.asyncio
async def test_invite_user_to_team_anti_collision_transforms_pending_application(fake_uow):
    event = make_event()
    captain = make_user()
    user = make_user()
    team = make_team(event, captain)
    registration = make_registration(user, event)
    existing = make_team_request(
        event,
        team,
        user,
        request_type=TeamRequestType.APPLICATION,
        status=TeamRequestStatus.PENDING_CAPTAIN,
        message="старое",
    )

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.users.find_one_or_none.return_value = user
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = registration
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.teams.get_members_count.return_value = 1
    fake_uow.requests.get_active_request.return_value = existing
    fake_uow.requests.get_by_id_with_relations.return_value = existing

    service = build_service(fake_uow)
    data = TeamInviteCreate(message="новое", target_role=ParticipantSpecialization.DESIGN)
    result = await service.invite_user_to_team(team.id, captain.id, user.id, data)

    assert result.status == TeamRequestStatus.PENDING_USER
    assert result.message == "новое"
    assert result.target_role == ParticipantSpecialization.DESIGN.value
    fake_uow.requests.update.assert_awaited_once()
    assert fake_uow.committed is True


@pytest.mark.asyncio
async def test_captain_approve_request(fake_uow):
    event = make_event()
    captain = make_user()
    candidate = make_user()
    team = make_team(event, captain, max_members=4)
    request = make_team_request(
        event,
        team,
        candidate,
        status=TeamRequestStatus.PENDING_CAPTAIN,
        request_type=TeamRequestType.APPLICATION,
    )
    candidate_registration = make_registration(candidate, event)

    fake_uow.requests.get_by_id_for_update.return_value = request
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = candidate_registration
    fake_uow.teams.get_members_count.return_value = 1
    fake_uow.requests.get_by_id_with_relations.return_value = request

    service = build_service(fake_uow)
    result = await service.captain_approve_request(request.id, captain.id)

    assert result.status == TeamRequestStatus.PENDING_USER
    fake_uow.requests.update.assert_awaited_once_with(
        request.id,
        {"status": TeamRequestStatus.PENDING_USER},
    )


@pytest.mark.asyncio
async def test_user_confirm_request_closes_target_role_and_cancels_overbooking(fake_uow):
    event = make_event(max_team_size=3)
    captain = make_user()
    user = make_user(
        specializations=[ParticipantSpecialization.BACKEND.value],
    )
    team = make_team(
        event,
        captain,
        max_members=3,
        needed_roles=[ParticipantSpecialization.DESIGN.value, ParticipantSpecialization.BACKEND.value],
    )
    request = make_team_request(
        event,
        team,
        user,
        target_role=ParticipantSpecialization.DESIGN.value,
        status=TeamRequestStatus.PENDING_USER,
        request_type=TeamRequestType.INVITE,
    )
    registration = make_registration(user, event)

    fake_uow.requests.get_by_id_for_update.return_value = request
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = registration
    fake_uow.users.find_one_or_none.return_value = user
    fake_uow.teams.get_members_count.return_value = 2
    fake_uow.requests.get_by_id_with_relations.return_value = request

    service = build_service(fake_uow)
    result = await service.user_confirm_request(request.id, user.id)

    assert result.status == TeamRequestStatus.ACCEPTED
    assert registration.team_id == team.id
    assert team.needed_roles == [ParticipantSpecialization.BACKEND.value]
    fake_uow.requests.cancel_other_user_requests.assert_awaited_once_with(
        event.id,
        user.id,
        exclude_request_id=request.id,
    )
    fake_uow.requests.cancel_team_pending_requests.assert_awaited_once_with(
        team.id,
        exclude_request_id=request.id,
    )


@pytest.mark.parametrize(
    "initial_status, actor_is_captain, expected_status",
    [
        (TeamRequestStatus.PENDING_CAPTAIN, False, TeamRequestStatus.CANCELLED),
        (TeamRequestStatus.PENDING_CAPTAIN, True, TeamRequestStatus.REJECTED),
        (TeamRequestStatus.PENDING_USER, True, TeamRequestStatus.CANCELLED),
        (TeamRequestStatus.PENDING_USER, False, TeamRequestStatus.REJECTED),
    ],
)
@pytest.mark.asyncio
async def test_reject_request_branches(
    fake_uow,
    initial_status,
    actor_is_captain,
    expected_status,
):
    event = make_event()
    captain = make_user()
    user = make_user()
    actor = captain if actor_is_captain else user
    team = make_team(event, captain)
    request = make_team_request(
        event,
        team,
        user,
        status=initial_status,
        request_type=TeamRequestType.APPLICATION,
    )

    fake_uow.requests.get_by_id_for_update.return_value = request
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.requests.get_by_id_with_relations.return_value = request

    service = build_service(fake_uow)
    result = await service.reject_request(request.id, actor.id)

    assert result.status == expected_status
    fake_uow.requests.update.assert_awaited_once_with(
        request.id,
        {"status": expected_status},
    )


@pytest.mark.asyncio
async def test_reject_request_third_party_denied(fake_uow):
    event = make_event()
    captain = make_user()
    user = make_user()
    third_party = make_user()
    team = make_team(event, captain)
    request = make_team_request(
        event,
        team,
        user,
        status=TeamRequestStatus.PENDING_CAPTAIN,
    )

    fake_uow.requests.get_by_id_for_update.return_value = request
    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = build_service(fake_uow)
    with pytest.raises(PermissionDeniedError):
        await service.reject_request(request.id, third_party.id)
