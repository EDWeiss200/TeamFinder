# Файл: backend/tests/test_team_services.py
"""Модульные тесты для TeamServices."""


import pytest

from schemas.team import TeamCreate, TeamUpdate
from services.team_services import TeamServices
from tests.conftest import (
    FakeUnitOfWork,
    make_event,
    make_registration,
    make_team,
    make_user,
)
from utils.exceptions import InvalidStateError, PermissionDeniedError


async def test_create_team_rejects_duplicate_name(fake_uow: FakeUnitOfWork):
    """create_team запрещает повторное имя команды в рамках одного мероприятия."""
    event = make_event()
    creator = make_user()
    registration = make_registration(creator, event)

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = registration
    fake_uow.teams.is_name_taken.return_value = True

    service = TeamServices(fake_uow)

    with pytest.raises(InvalidStateError, match="таким названием уже существует"):
        await service.create_team(
            event_id=event.id,
            creator_id=creator.id,
            team_data=TeamCreate(
                name="Drill Flex",
                description="desc",
                max_members=4,
                needed_roles=[],
                allow_auto_match=True,
            ),
        )


async def test_create_team_rejects_max_members_below_event_min(fake_uow: FakeUnitOfWork):
    """create_team проверяет нижнюю границу размера команды."""
    event = make_event(min_team_size=3)
    creator = make_user()
    registration = make_registration(creator, event)

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = registration
    fake_uow.teams.is_name_taken.return_value = False

    service = TeamServices(fake_uow)

    with pytest.raises(InvalidStateError, match="меньше минимального размера"):
        await service.create_team(
            event_id=event.id,
            creator_id=creator.id,
            team_data=TeamCreate(
                name="Mini Team",
                description="desc",
                max_members=2,
                needed_roles=[],
                allow_auto_match=True,
            ),
        )


async def test_get_event_teams_returns_paginated_response(fake_uow: FakeUnitOfWork):
    """get_event_teams возвращает пагинацию и прокидывает фильтры в репозиторий."""
    event = make_event()
    captain = make_user()
    team = make_team(event, captain)

    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.teams.get_by_event_id.return_value = [team]
    fake_uow.teams.count_by_event.return_value = 1

    service = TeamServices(fake_uow)
    result = await service.get_event_teams(
        event_id=event.id,
        needed_role="backend",
        has_free_slots=True,
        page=2,
        size=5,
    )

    assert result.total == 1
    assert result.page == 2
    assert result.size == 5
    assert result.items == [team]
    fake_uow.teams.get_by_event_id.assert_awaited_once_with(
        event_id=event.id,
        needed_role="backend",
        has_free_slots=True,
        limit=5,
        offset=5,
    )


async def test_get_team_detail_masks_invite_token_for_outsider(fake_uow: FakeUnitOfWork):
    """get_team_detail скрывает invite_token для постороннего пользователя."""
    event = make_event()
    captain = make_user()
    outsider = make_user()
    team = make_team(event, captain)
    captain_reg = make_registration(captain, event, team_id=team.id)
    team.members = [captain_reg]

    fake_uow.teams.get_by_id_with_members.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)
    result = await service.get_team_detail(team_id=team.id, current_user=outsider)

    assert result["invite_token"] is None
    assert result["is_user_member"] is False
    assert result["is_user_captain"] is False


async def test_get_team_detail_shows_invite_token_for_member(fake_uow: FakeUnitOfWork):
    """get_team_detail показывает invite_token участнику команды."""
    event = make_event()
    captain = make_user()
    team = make_team(event, captain)
    captain_reg = make_registration(captain, event, team_id=team.id)
    team.members = [captain_reg]

    fake_uow.teams.get_by_id_with_members.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)
    result = await service.get_team_detail(team_id=team.id, current_user=captain)

    assert result["invite_token"] == team.invite_token
    assert result["is_user_member"] is True
    assert result["is_user_captain"] is True


async def test_update_team_success_by_organizer(fake_uow: FakeUnitOfWork):
    """update_team разрешает организатору менять команду и фиксирует изменения."""
    organizer = make_user()
    event = make_event(organizer_id=organizer.id, min_team_size=3, max_team_size=5)
    captain = make_user()
    member = make_user()
    team = make_team(event, captain, max_members=5)
    team.members = [
        make_registration(captain, event, team_id=team.id),
        make_registration(member, event, team_id=team.id),
    ]
    updated_team = make_team(event, captain, name="New Name", max_members=4)
    updated_team.members = team.members

    fake_uow.teams.get_by_id_with_members.side_effect = [team, updated_team]
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.teams.is_name_taken.return_value = False

    service = TeamServices(fake_uow)
    result = await service.update_team(
        team_id=team.id,
        actor_user=organizer,
        update_data=TeamUpdate(name="New Name", max_members=4),
    )

    assert result.name == "New Name"
    fake_uow.teams.update.assert_awaited_once_with(
        team.id,
        {"name": "New Name", "max_members": 4},
    )
    assert fake_uow.committed is True


async def test_update_team_rejects_if_new_name_taken(fake_uow: FakeUnitOfWork):
    """update_team валидирует уникальность нового названия."""
    event = make_event()
    captain = make_user()
    team = make_team(event, captain)

    fake_uow.teams.get_by_id_with_members.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.teams.is_name_taken.return_value = True

    service = TeamServices(fake_uow)

    with pytest.raises(InvalidStateError, match="таким названием уже существует"):
        await service.update_team(
            team_id=team.id,
            actor_user=captain,
            update_data=TeamUpdate(name="Occupied Name"),
        )


async def test_update_team_rejects_when_max_members_below_current_count(
    fake_uow: FakeUnitOfWork,
):
    """update_team не позволяет уменьшить лимит ниже текущего числа участников."""
    event = make_event(min_team_size=3, max_team_size=5)
    captain = make_user()
    member = make_user()
    team = make_team(event, captain, max_members=5)
    team.members = [
        make_registration(captain, event, team_id=team.id),
        make_registration(member, event, team_id=team.id),
    ]

    fake_uow.teams.get_by_id_with_members.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)

    with pytest.raises(InvalidStateError, match="меньше текущего количества"):
        await service.update_team(
            team_id=team.id,
            actor_user=captain,
            update_data=TeamUpdate(max_members=1),
        )


async def test_update_team_rejects_for_non_manager(fake_uow: FakeUnitOfWork):
    """update_team запрещён постороннему пользователю."""
    event = make_event()
    captain = make_user()
    outsider = make_user()
    team = make_team(event, captain)

    fake_uow.teams.get_by_id_with_members.return_value = team
    fake_uow.events.find_one_or_none.return_value = event

    service = TeamServices(fake_uow)

    with pytest.raises(PermissionDeniedError):
        await service.update_team(
            team_id=team.id,
            actor_user=outsider,
            update_data=TeamUpdate(description="updated"),
        )


async def test_regenerate_invite_token_success(fake_uow: FakeUnitOfWork):
    """regenerate_invite_token доступен капитану и коммитит новый токен."""
    event = make_event()
    captain = make_user()
    team = make_team(event, captain)

    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.teams.find_one_or_none.return_value = None

    service = TeamServices(fake_uow)
    token = await service.regenerate_invite_token(
        team_id=team.id,
        actor_user_id=captain.id,
    )

    assert token
    fake_uow.teams.update.assert_awaited_once_with(team.id, {"invite_token": token})
    assert fake_uow.committed is True


async def test_regenerate_invite_token_rejects_non_captain(fake_uow: FakeUnitOfWork):
    """regenerate_invite_token запрещён некапитану."""
    event = make_event()
    captain = make_user()
    outsider = make_user()
    team = make_team(event, captain)

    fake_uow.teams.get_by_id_for_update.return_value = team

    service = TeamServices(fake_uow)

    with pytest.raises(PermissionDeniedError, match="Только капитан"):
        await service.regenerate_invite_token(
            team_id=team.id,
            actor_user_id=outsider.id,
        )

async def test_join_by_invite_token_closes_one_role_and_cancels_requests(
    fake_uow: FakeUnitOfWork,
):
    """join_by_invite_token закрывает ровно одну роль из needed_roles и отменяет заявки при заполнении."""
    event = make_event(min_team_size=2, max_team_size=2)
    captain = make_user()
    new_member = make_user(specializations=["backend", "design"])
    team = make_team(
        event,
        captain,
        max_members=2,
        needed_roles=["backend", "design"],
    )

    fake_uow.teams.get_by_invite_token_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.users.find_one_or_none.return_value = new_member
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = None
    fake_uow.teams.get_members_count.return_value = 1  # после входа станет 2 из 2 (команда полная)
    fake_uow.teams.get_by_id_with_members.return_value = team

    service = TeamServices(fake_uow)
    await service.join_by_invite_token(
        invite_token=team.invite_token,
        user_id=new_member.id,
    )

    # Закрылась только ОДНА роль ('backend'), а 'design' осталась
    fake_uow.teams.update.assert_awaited_once_with(
        team.id, {"needed_roles": ["design"]}
    )
    fake_uow.requests.cancel_other_user_requests.assert_awaited_once_with(
        event.id, new_member.id
    )
    fake_uow.requests.cancel_team_pending_requests.assert_awaited_once_with(team.id)
    assert fake_uow.committed is True


async def test_leave_team_transfers_captaincy_to_oldest_member(
    fake_uow: FakeUnitOfWork,
):
    """При выходе капитана права передаются участнику с самым ранним joined_team_at."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    event = make_event()
    captain = make_user()
    member_old = make_user()
    member_new = make_user()
    team = make_team(event, captain)

    reg_captain = make_registration(
        captain, event, team_id=team.id, joined_team_at=now - timedelta(hours=3)
    )
    reg_old = make_registration(
        member_old, event, team_id=team.id, joined_team_at=now - timedelta(hours=2)
    )
    reg_new = make_registration(
        member_new, event, team_id=team.id, joined_team_at=now - timedelta(hours=1)
    )
    team.members = [reg_captain, reg_old, reg_new]

    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = reg_captain
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.teams.get_by_id_with_members.return_value = team

    service = TeamServices(fake_uow)
    await service.leave_team(team_id=team.id, user_id=captain.id)

    fake_uow.teams.update.assert_awaited_once_with(
        team.id, {"captain_id": member_old.id}
    )
    assert fake_uow.committed is True


async def test_leave_team_deletes_team_when_last_member_leaves(
    fake_uow: FakeUnitOfWork,
):
    """Если капитан был единственным участником, при выходе команда удаляется."""
    event = make_event()
    captain = make_user()
    team = make_team(event, captain)
    reg_captain = make_registration(captain, event, team_id=team.id)
    team.members = [reg_captain]

    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = reg_captain
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.teams.get_by_id_with_members.return_value = team

    service = TeamServices(fake_uow)
    result = await service.leave_team(team_id=team.id, user_id=captain.id)

    assert result is None
    fake_uow.requests.cancel_team_pending_requests.assert_awaited_once_with(team.id)
    fake_uow.teams.delete_one.assert_awaited_once_with(team.id)
    assert fake_uow.committed is True


async def test_kick_member_success_by_captain(fake_uow: FakeUnitOfWork):
    """Капитан успешно исключает участника из команды."""
    event = make_event()
    captain = make_user()
    target = make_user()
    team = make_team(event, captain)

    reg_captain = make_registration(captain, event, team_id=team.id)
    reg_target = make_registration(target, event, team_id=team.id)
    team.members = [reg_captain, reg_target]

    fake_uow.teams.get_by_id_for_update.return_value = team
    fake_uow.events.find_one_or_none.return_value = event
    fake_uow.registrations.get_by_event_and_user_for_update.return_value = reg_target
    fake_uow.teams.get_by_id_with_members.return_value = team

    service = TeamServices(fake_uow)
    await service.kick_member(
        team_id=team.id,
        actor_user_id=captain.id,
        member_user_id=target.id,
    )

    fake_uow.registrations.update.assert_awaited_once_with(
        reg_target.id, {"team_id": None, "joined_team_at": None}
    )
    assert fake_uow.committed is True