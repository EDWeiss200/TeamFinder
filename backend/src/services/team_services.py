"""Сервисный слой для работы с командами, инвайтами и составом."""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from models.enums import EventStatus
from models.team import Team
from services.event_services import EventServices
from schemas.team import TeamCreate
from utils.exceptions import (
    AlreadyInTeamError,
    EntityNotFoundError,
    InvalidStateError,
    PermissionDeniedError,
    TeamIsFullError,
)
from utils.uow import IUnitOfWork


class TeamServices:
    """Сервис управления командами и жизненным циклом состава."""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow

    def _ensure_registration_phase(self, event) -> None:
        """Проверить, что операция выполняется в фазе регистрации."""
        now = datetime.now(timezone.utc)
        if event.status != EventStatus.REGISTRATION or now > event.registration_end:
            raise InvalidStateError(
                "Операция доступна только во время фазы регистрации мероприятия"
            )

    async def _sync_event_state(self, event) -> None:
        """Применить ленивые переходы статуса мероприятия перед командной операцией."""
        await EventServices(self.uow)._apply_lazy_status_transitions(event)

    async def _generate_unique_invite_token(self) -> str:
        """Сгенерировать уникальный секретный токен приглашения."""
        while True:
            token = secrets.token_hex(32)
            existing = await self.uow.teams.find_one_or_none(invite_token=token)
            if not existing:
                return token

    @staticmethod
    def _close_one_needed_role(needed_roles: list[str], user_specializations: list[str]) -> None:
        """Удалить не более одной закрываемой роли из needed_roles."""
        for specialization in user_specializations:
            if specialization in needed_roles:
                needed_roles.remove(specialization)
                break

    async def create_team(
        self,
        event_id: uuid.UUID,
        creator_id: uuid.UUID,
        team_data: TeamCreate,
    ) -> Team:
        """Создать команду и автоматически зачислить создателя как капитана."""
        async with self.uow:
            event = await self.uow.events.find_one_or_none(id=event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {event_id} не найдено")
            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            registration = await self.uow.registrations.get_by_event_and_user_for_update(
                event_id=event_id,
                user_id=creator_id,
            )
            if not registration:
                raise InvalidStateError(
                    "Чтобы создать команду, нужно сначала зарегистрироваться на мероприятие"
                )
            if registration.team_id is not None:
                raise AlreadyInTeamError()

            if team_data.max_members > event.max_team_size:
                raise InvalidStateError(
                    "Желаемый размер команды не может превышать лимит мероприятия"
                )

            invite_token = await self._generate_unique_invite_token()
            team_payload = team_data.model_dump(mode="json")
            team_payload.update(
                {
                    "event_id": event_id,
                    "captain_id": creator_id,
                    "invite_token": invite_token,
                }
            )
            team = await self.uow.teams.add_one(team_payload)

            now = datetime.now(timezone.utc)
            await self.uow.registrations.update(
                registration.id,
                {
                    "team_id": team.id,
                    "joined_team_at": now,
                },
            )
            await self.uow.requests.cancel_other_user_requests(event_id, creator_id)
            await self.uow.commit()

            return await self.uow.teams.get_by_id_with_members(team.id)

    async def join_by_invite_token(
        self,
        invite_token: str,
        user_id: uuid.UUID,
    ) -> Team:
        """Вступить в команду по секретному invite_token."""
        async with self.uow:
            team = await self.uow.teams.get_by_invite_token_for_update(invite_token)
            if not team:
                raise EntityNotFoundError("Команда по указанному invite_token не найдена")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {team.event_id} не найдено")
            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            registration = await self.uow.registrations.get_by_event_and_user_for_update(
                event_id=event.id,
                user_id=user_id,
            )
            if registration and registration.team_id is not None:
                raise AlreadyInTeamError()

            current_members_count = await self.uow.teams.get_members_count(team.id)
            limit = min(team.max_members, event.max_team_size)
            if current_members_count >= limit:
                raise TeamIsFullError()

            now = datetime.now(timezone.utc)
            if registration is None:
                registration = await self.uow.registrations.add_one(
                    {
                        "event_id": event.id,
                        "user_id": user_id,
                        "team_id": team.id,
                        "joined_team_at": now,
                    }
                )
            else:
                await self.uow.registrations.update(
                    registration.id,
                    {
                        "team_id": team.id,
                        "joined_team_at": now,
                    },
                )

            needed_roles = list(team.needed_roles or [])
            self._close_one_needed_role(needed_roles, list(user.specializations or []))
            await self.uow.teams.update(team.id, {"needed_roles": needed_roles})

            await self.uow.requests.cancel_other_user_requests(event.id, user_id)

            if current_members_count + 1 >= limit:
                await self.uow.requests.cancel_team_pending_requests(team.id)

            await self.uow.commit()
            return await self.uow.teams.get_by_id_with_members(team.id)

    async def leave_team(self, team_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Team]:
        """Выйти из команды с автопередачей капитанства или удалением пустой команды."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_for_update(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")

            registration = await self.uow.registrations.get_by_event_and_user_for_update(
                event_id=team.event_id,
                user_id=user_id,
            )
            if not registration or registration.team_id is None:
                raise InvalidStateError("Вы не состоите в этой команде")
            if registration.team_id != team.id:
                raise InvalidStateError("Вы не состоите в этой команде")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {team.event_id} не найдено")
            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            team_with_members = await self.uow.teams.get_by_id_with_members(team.id)
            if not team_with_members:
                raise EntityNotFoundError(f"Команда с ID {team.id} не найдена")

            remaining_members = [
                member for member in team_with_members.members if member.user_id != user_id
            ]

            await self.uow.registrations.update(
                registration.id,
                {
                    "team_id": None,
                    "joined_team_at": None,
                },
            )

            if team.captain_id == user_id:
                if not remaining_members:
                    await self.uow.requests.cancel_team_pending_requests(team.id)
                    await self.uow.teams.delete_one(team.id)
                    await self.uow.commit()
                    return None

                new_captain = min(
                    remaining_members,
                    key=lambda member: member.joined_team_at
                    or datetime.max.replace(tzinfo=timezone.utc),
                )
                await self.uow.teams.update(team.id, {"captain_id": new_captain.user_id})

            await self.uow.commit()
            return await self.uow.teams.get_by_id_with_members(team.id)

    async def kick_member(
        self,
        team_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        member_user_id: uuid.UUID,
    ) -> Optional[Team]:
        """Исключить участника из команды капитаном."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_for_update(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {team.event_id} не найдено")
            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            if team.captain_id != actor_user_id:
                raise PermissionDeniedError("Только капитан команды может исключать участников")
            if member_user_id == actor_user_id:
                raise InvalidStateError("Капитан не может исключить сам себя")

            target_registration = await self.uow.registrations.get_by_event_and_user_for_update(
                event_id=event.id,
                user_id=member_user_id,
            )
            if not target_registration or target_registration.team_id != team.id:
                raise InvalidStateError("Пользователь не состоит в этой команде")

            team_with_members = await self.uow.teams.get_by_id_with_members(team.id)
            if not team_with_members:
                raise EntityNotFoundError(f"Команда с ID {team.id} не найдена")

            remaining_members = [
                member for member in team_with_members.members if member.user_id != member_user_id
            ]

            await self.uow.registrations.update(
                target_registration.id,
                {
                    "team_id": None,
                    "joined_team_at": None,
                },
            )

            if not remaining_members:
                await self.uow.requests.cancel_team_pending_requests(team.id)
                await self.uow.teams.delete_one(team.id)
                await self.uow.commit()
                return None

            await self.uow.commit()
            return await self.uow.teams.get_by_id_with_members(team.id)
