"""Сервисный слой для работы с командами, инвайтами и составом."""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from models.enums import EventStatus, TeamRequestStatus, TeamRequestType
from models.team import Team, TeamRequest
from models.user import User
from schemas.common import PaginatedResponse
from services.event_services import EventServices
from schemas.team import (
    TeamApplicationCreate,
    TeamCreate,
    TeamDetailRead,
    TeamInviteCreate,
    TeamUpdate,
)
from utils.exceptions import (
    AlreadyInTeamError,
    EntityNotFoundError,
    InvalidStateError,
    PermissionDeniedError,
    RegistrationClosedError,
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
            raise RegistrationClosedError(
                "Регистрация на это мероприятие закрыта "
                f"(текущий статус: {event.status.value})"
            )
        
    async def _sync_event_state(self, event) -> None:
        """Применить ленивые переходы статуса мероприятия перед командной операцией."""
        await EventServices(self.uow)._apply_lazy_status_transitions(event)

    async def _generate_unique_invite_token(self) -> str:
        """Сгенерировать уникальный секретный токен приглашения (максимум 10 попыток)."""
        for _ in range(10):
            token = secrets.token_hex(32)
            existing = await self.uow.teams.find_one_or_none(invite_token=token)
            if existing is None or not isinstance(existing, Team):
                return token
        raise InvalidStateError("Не удалось сгенерировать уникальный токен приглашения")

    @staticmethod
    def _close_one_needed_role(
        needed_roles: list[str],
        user_specializations: list[str],
        target_role: Optional[str] = None,
    ) -> None:
        """Удалить не более одной закрываемой роли из needed_roles."""
        if target_role is not None and target_role in needed_roles:
            needed_roles.remove(target_role)
            return
        for specialization in user_specializations:
            if specialization in needed_roles:
                needed_roles.remove(specialization)
                break

    @staticmethod
    def _can_manage_team(team: Team, event: Any, actor_user: User) -> bool:
        """Проверить право управления командой."""
        return bool(
            actor_user.is_superuser
            or team.captain_id == actor_user.id
            or event.organizer_id == actor_user.id
        )

    @staticmethod
    def _build_team_detail_payload(
        team: Team,
        event: Any,
        current_user: Optional[User],
    ) -> dict:
        """Собрать безопасный payload для TeamDetailRead."""
        team_payload = TeamDetailRead.model_validate(team).model_dump()

        is_user_member = bool(
            current_user
            and any(
                member.user_id == current_user.id for member in (team.members or [])
            )
        )
        is_user_captain = bool(current_user and team.captain_id == current_user.id)
        can_view_invite_token = bool(
            current_user
            and (
                is_user_member
                or event.organizer_id == current_user.id
                or current_user.is_superuser
            )
        )

        team_payload.update(
            {
                "invite_token": team.invite_token if can_view_invite_token else None,
                "is_user_member": is_user_member,
                "is_user_captain": is_user_captain,
            }
        )
        return team_payload

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

            registration = (
                await self.uow.registrations.get_by_event_and_user_for_update(
                    event_id=event_id,
                    user_id=creator_id,
                )
            )
            if not registration:
                raise InvalidStateError(
                    "Чтобы создать команду, нужно сначала зарегистрироваться на мероприятие"
                )
            if registration.team_id is not None:
                raise AlreadyInTeamError()

            if await self.uow.teams.is_name_taken(event_id, team_data.name):
                raise InvalidStateError(
                    "Команда с таким названием уже существует на этом мероприятии"
                )

            if team_data.max_members < event.min_team_size:
                raise InvalidStateError(
                    "Желаемый размер команды не может быть меньше минимального размера команды на мероприятии"
                )
            if team_data.max_members > event.max_team_size:
                raise InvalidStateError(
                    "Желаемый размер команды не может превышать лимит мероприятия"
                )
            if len(team_data.needed_roles) > team_data.max_members - 1:
                raise InvalidStateError(
                    "Количество искомых ролей превышает число свободных мест в команде"
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

    async def get_event_teams(
        self,
        event_id: uuid.UUID,
        needed_role=None,
        has_free_slots=None,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse[Team]:
        """Получить каталог команд мероприятия с пагинацией и фильтрами."""
        offset = (page - 1) * size
        async with self.uow:
            event = await self.uow.events.find_one_or_none(id=event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {event_id} не найдено")

            await self._sync_event_state(event)

            normalized_needed_role = (
                needed_role.value if hasattr(needed_role, "value") else needed_role
            )
            items = await self.uow.teams.get_by_event_id(
                event_id=event_id,
                needed_role=normalized_needed_role,
                has_free_slots=has_free_slots,
                limit=size,
                offset=offset,
            )
            total = await self.uow.teams.count_by_event(
                event_id=event_id,
                needed_role=normalized_needed_role,
                has_free_slots=has_free_slots,
            )
            return PaginatedResponse.create(
                items=items,
                total=total,
                page=page,
                size=size,
            )

    async def get_my_requests(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[TeamRequest]:
        """Получить мои заявки или входящие заявки моей команды."""
        async with self.uow:
            event = await self.uow.events.find_one_or_none(id=event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {event_id} не найдено")

            await self._sync_event_state(event)

            reg = await self.uow.registrations.get_by_event_and_user(event_id, user_id)
            if reg and reg.team_id and reg.team and reg.team.captain_id == user_id:
                return await self.uow.requests.get_team_incoming_requests(reg.team_id)
            return await self.uow.requests.get_user_event_requests(event_id, user_id)

    async def apply_to_team(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        data: Optional[TeamApplicationCreate] = None,
    ) -> TeamRequest:
        """Подать отклик в команду или автоматически принять ожидающее приглашение."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_for_update(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )

            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            registration = await self.uow.registrations.get_by_event_and_user_for_update(
                event.id, user_id
            )
            if not registration:
                raise InvalidStateError(
                    "Чтобы откликнуться на команду, нужно зарегистрироваться на мероприятие"
                )
            if registration.team_id is not None:
                raise AlreadyInTeamError()

            current_members_count = await self.uow.teams.get_members_count(team.id)
            limit = min(team.max_members, event.max_team_size)
            if current_members_count >= limit:
                raise TeamIsFullError()

            existing = await self.uow.requests.get_active_request(team.id, user_id)
            if existing:
                if existing.status == TeamRequestStatus.PENDING_CAPTAIN:
                    raise InvalidStateError(
                        "Активный отклик в эту команду уже существует"
                    )
                if existing.status == TeamRequestStatus.PENDING_USER:
                    now = datetime.now(timezone.utc)
                    registration.team_id = team.id
                    registration.joined_team_at = now
                    await self.uow.registrations.update(
                        registration.id,
                        {"team_id": team.id, "joined_team_at": now},
                    )

                    target_role = existing.target_role or (
                        getattr(data.target_role, "value", data.target_role)
                        if data and data.target_role is not None
                        else None
                    )

                    update_req_payload = {"status": TeamRequestStatus.ACCEPTED}
                    if target_role is not None:
                        update_req_payload["target_role"] = target_role
                    if data and data.message is not None:
                        update_req_payload["message"] = data.message
                    await self.uow.requests.update(existing.id, update_req_payload)

                    needed_roles = list(team.needed_roles or [])
                    self._close_one_needed_role(
                        needed_roles,
                        list(getattr(user, "specializations", []) or []),
                        target_role=target_role,
                    )
                    team.needed_roles = needed_roles
                    await self.uow.teams.update(team.id, {"needed_roles": needed_roles})

                    existing.status = TeamRequestStatus.ACCEPTED
                    await self.uow.requests.cancel_other_user_requests(
                        event.id,
                        user_id,
                        exclude_request_id=existing.id,
                    )
                    if current_members_count + 1 >= limit:
                        await self.uow.requests.cancel_team_pending_requests(
                            team.id,
                            exclude_request_id=existing.id,
                        )
                    await self.uow.commit()
                    return await self.uow.requests.get_by_id_with_relations(existing.id)

            request_payload = {
                "event_id": event.id,
                "team_id": team.id,
                "user_id": user_id,
                "target_role": getattr(data.target_role, "value", data.target_role)
                if data and data.target_role is not None
                else None,
                "message": data.message if data else None,
                "request_type": TeamRequestType.APPLICATION,
                "status": TeamRequestStatus.PENDING_CAPTAIN,
            }
            request = await self.uow.requests.add_one(request_payload)
            await self.uow.commit()
            return await self.uow.requests.get_by_id_with_relations(request.id)

    async def invite_user_to_team(
        self,
        team_id: uuid.UUID,
        captain_id: uuid.UUID,
        target_user_id: uuid.UUID,
        data: Optional[TeamInviteCreate] = None,
    ) -> TeamRequest:
        """Отправить приглашение участнику или превратить встречный отклик в приглашение."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_for_update(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")
            if team.captain_id != captain_id:
                raise PermissionDeniedError(
                    "Отправлять приглашения может только капитан команды"
                )

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )

            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            target_user = await self.uow.users.find_one_or_none(id=target_user_id)
            if not target_user:
                raise EntityNotFoundError(f"Пользователь с ID {target_user_id} не найден")

            registration = await self.uow.registrations.get_by_event_and_user_for_update(
                event.id, target_user_id
            )
            if not registration:
                raise InvalidStateError(
                    "Пользователь не зарегистрирован на мероприятие"
                )
            if registration.team_id is not None:
                raise AlreadyInTeamError()

            current_members_count = await self.uow.teams.get_members_count(team.id)
            limit = min(team.max_members, event.max_team_size)
            if current_members_count >= limit:
                raise TeamIsFullError()

            existing = await self.uow.requests.get_active_request(team.id, target_user_id)
            if existing:
                if existing.status == TeamRequestStatus.PENDING_USER:
                    raise InvalidStateError(
                        "Приглашение этому участнику уже отправлено"
                    )
                if existing.status == TeamRequestStatus.PENDING_CAPTAIN:
                    update_payload = {"status": TeamRequestStatus.PENDING_USER}
                    if data and data.message is not None:
                        update_payload["message"] = data.message
                    if data and data.target_role is not None:
                        update_payload["target_role"] = getattr(
                            data.target_role, "value", data.target_role
                        )
                    await self.uow.requests.update(existing.id, update_payload)
                    existing.status = TeamRequestStatus.PENDING_USER
                    if "message" in update_payload:
                        existing.message = update_payload["message"]
                    if "target_role" in update_payload:
                        existing.target_role = update_payload["target_role"]
                    await self.uow.commit()
                    return await self.uow.requests.get_by_id_with_relations(existing.id)

            request_payload = {
                "event_id": event.id,
                "team_id": team.id,
                "user_id": target_user_id,
                "target_role": getattr(data.target_role, "value", data.target_role)
                if data and data.target_role is not None
                else None,
                "message": data.message if data else None,
                "request_type": TeamRequestType.INVITE,
                "status": TeamRequestStatus.PENDING_USER,
            }
            request = await self.uow.requests.add_one(request_payload)
            await self.uow.commit()
            return await self.uow.requests.get_by_id_with_relations(request.id)

    async def captain_approve_request(
        self,
        request_id: uuid.UUID,
        captain_id: uuid.UUID,
    ) -> TeamRequest:
        """Перевести отклик капитаном из PENDING_CAPTAIN в PENDING_USER."""
        async with self.uow:
            req = await self.uow.requests.get_by_id_for_update(request_id)
            if not req:
                raise EntityNotFoundError(f"Заявка с ID {request_id} не найдена")

            team = await self.uow.teams.get_by_id_for_update(req.team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {req.team_id} не найдена")
            if team.captain_id != captain_id:
                raise PermissionDeniedError(
                    "Одобрять заявку может только капитан команды"
                )

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )

            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            if req.status != TeamRequestStatus.PENDING_CAPTAIN:
                raise InvalidStateError("Заявку нельзя одобрить в текущем статусе")

            target_registration = (
                await self.uow.registrations.get_by_event_and_user_for_update(
                    event.id,
                    req.user_id,
                )
            )
            if not target_registration:
             raise InvalidStateError("Кандидат не зарегистрирован на мероприятие")
            if target_registration.team_id is not None:
             raise AlreadyInTeamError()

            current_members_count = await self.uow.teams.get_members_count(team.id)
            limit = min(team.max_members, event.max_team_size)
            if current_members_count >= limit:
                raise TeamIsFullError()

            await self.uow.requests.update(
                req.id,
                {"status": TeamRequestStatus.PENDING_USER},
            )
            req.status = TeamRequestStatus.PENDING_USER
            await self.uow.commit()
            return await self.uow.requests.get_by_id_with_relations(request_id)

    async def user_confirm_request(
        self,
        request_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TeamRequest:
        """Подтвердить приглашение или одобренный отклик участником."""
        async with self.uow:
            req = await self.uow.requests.get_by_id_for_update(request_id)
            if not req:
                raise EntityNotFoundError(f"Заявка с ID {request_id} не найдена")
            if req.user_id != user_id:
                raise PermissionDeniedError(
                    "Подтверждать заявку может только её адресат"
                )
            if req.status != TeamRequestStatus.PENDING_USER:
                raise InvalidStateError("Заявку нельзя подтвердить в текущем статусе")

            team = await self.uow.teams.get_by_id_for_update(req.team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {req.team_id} не найдена")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )

            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            registration = (
                await self.uow.registrations.get_by_event_and_user_for_update(
                    event.id, user_id
                )
            )
            if not registration:
                raise InvalidStateError(
                    "Чтобы подтвердить заявку, нужно быть зарегистрированным на мероприятии"
                )
            if registration.team_id is not None:
                raise AlreadyInTeamError()

            current_members_count = await self.uow.teams.get_members_count(team.id)
            limit = min(team.max_members, event.max_team_size)
            if current_members_count >= limit:
                raise TeamIsFullError()

            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            now = datetime.now(timezone.utc)
            registration.team_id = team.id
            registration.joined_team_at = now
            await self.uow.registrations.update(
                registration.id,
                {"team_id": team.id, "joined_team_at": now},
            )

            needed_roles = list(team.needed_roles or [])
            self._close_one_needed_role(
                needed_roles,
                list(getattr(user, "specializations", []) or []),
                target_role=req.target_role,
            )
            team.needed_roles = needed_roles
            await self.uow.teams.update(team.id, {"needed_roles": needed_roles})

            await self.uow.requests.update(
                req.id,
                {"status": TeamRequestStatus.ACCEPTED},
            )
            req.status = TeamRequestStatus.ACCEPTED
            await self.uow.requests.cancel_other_user_requests(
                event.id,
                user_id,
                exclude_request_id=req.id,
            )
            if current_members_count + 1 >= limit:
                await self.uow.requests.cancel_team_pending_requests(
                    team.id,
                    exclude_request_id=req.id,
                )

            await self.uow.commit()
            return await self.uow.requests.get_by_id_with_relations(request_id)

    async def reject_request(
        self,
        request_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> TeamRequest:
        """Отклонить или отменить активную заявку/приглашение."""
        async with self.uow:
            req = await self.uow.requests.get_by_id_for_update(request_id)
            if not req:
                raise EntityNotFoundError(f"Заявка с ID {request_id} не найдена")

            team = await self.uow.teams.get_by_id_for_update(req.team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {req.team_id} не найдена")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )

            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            if req.status not in (
                TeamRequestStatus.PENDING_CAPTAIN,
                TeamRequestStatus.PENDING_USER,
            ):
                raise InvalidStateError("Заявку нельзя отклонить в текущем статусе")

            if req.status == TeamRequestStatus.PENDING_CAPTAIN:
                if actor_user_id == req.user_id:
                    new_status = TeamRequestStatus.CANCELLED
                elif actor_user_id == team.captain_id:
                    new_status = TeamRequestStatus.REJECTED
                else:
                    raise PermissionDeniedError(
                        "Отклонять заявку может только её адресат или капитан команды"
                    )
            else:
                if actor_user_id == team.captain_id:
                    new_status = TeamRequestStatus.CANCELLED
                elif actor_user_id == req.user_id:
                    new_status = TeamRequestStatus.REJECTED
                else:
                    raise PermissionDeniedError(
                        "Отклонять приглашение может только капитан команды или его адресат"
                    )

            await self.uow.requests.update(req.id, {"status": new_status})
            req.status = new_status
            await self.uow.commit()
            return await self.uow.requests.get_by_id_with_relations(request_id)

    async def get_team_detail(
        self,
        team_id: uuid.UUID,
        current_user: Optional[User],
    ) -> dict:
        """Получить детальную информацию о команде с безопасной маскировкой invite_token."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_with_members(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )

            await self._sync_event_state(event)
            return self._build_team_detail_payload(team, event, current_user)

    async def update_team(
        self,
        team_id: uuid.UUID,
        actor_user: User,
        update_data: TeamUpdate,
    ) -> Team:
        """Обновить данные команды капитаном, организатором мероприятия или суперпользователем."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_with_members(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )

            if not self._can_manage_team(team, event, actor_user):
                raise PermissionDeniedError(
                    "Редактировать команду может только капитан, организатор мероприятия или суперпользователь"
                )
            
            await self._sync_event_state(event)
            if not (actor_user.is_superuser or event.organizer_id == actor_user.id):
                self._ensure_registration_phase(event)

            update_payload = update_data.model_dump(mode="json", exclude_unset=True)

            new_name = update_payload.get("name")
            if new_name and await self.uow.teams.is_name_taken(
                event_id=event.id,
                name=new_name,
                exclude_team_id=team_id,
            ):
                raise InvalidStateError(
                    "Команда с таким названием уже существует на этом мероприятии"
                )

            if "max_members" in update_payload:
                members_count = len(team.members or [])
                new_max_members = update_payload["max_members"]
                if new_max_members < members_count:
                    raise InvalidStateError(
                        "Нельзя установить размер команды меньше текущего количества участников"
                    )
                if not (event.min_team_size <= new_max_members <= event.max_team_size):
                    raise InvalidStateError(
                        "Размер команды должен соответствовать ограничениям мероприятия"
                    )

            if update_payload:
                await self.uow.teams.update(team_id, update_payload)
                await self.uow.commit()

            updated_team = await self.uow.teams.get_by_id_with_members(team_id)
            if not updated_team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")
            return updated_team

    async def regenerate_invite_token(
        self,
        team_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> str:
        """Перевыпустить invite_token команды. Разрешено только капитану в фазе регистрации."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_for_update(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")

            # Проверяем статус мероприятия и ленивые дедлайны:
            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(f"Мероприятие с ID {team.event_id} не найдено")
            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            if team.captain_id != actor_user_id:
                raise PermissionDeniedError(
                    "Только капитан команды может перевыпускать invite_token"
                )

            token = await self._generate_unique_invite_token()
            await self.uow.teams.update(team_id, {"invite_token": token})
            await self.uow.commit()
            return token

    async def join_by_invite_token(
        self,
        invite_token: str,
        user_id: uuid.UUID,
    ) -> Team:
        """Вступить в команду по секретному invite_token."""
        async with self.uow:
            team = await self.uow.teams.get_by_invite_token_for_update(invite_token)
            if not team:
                raise EntityNotFoundError(
                    "Команда по указанному invite_token не найдена"
                )

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )
            await self._sync_event_state(event)

            self._ensure_registration_phase(event)

            user = await self.uow.users.find_one_or_none(id=user_id)
            if not user:
                raise EntityNotFoundError(f"Пользователь с ID {user_id} не найден")

            registration = (
                await self.uow.registrations.get_by_event_and_user_for_update(
                    event_id=event.id,
                    user_id=user_id,
                )
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

    async def leave_team(
        self, team_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[Team]:
        """Выйти из команды с автопередачей капитанства или удалением пустой команды."""
        async with self.uow:
            team = await self.uow.teams.get_by_id_for_update(team_id)
            if not team:
                raise EntityNotFoundError(f"Команда с ID {team_id} не найдена")

            registration = (
                await self.uow.registrations.get_by_event_and_user_for_update(
                    event_id=team.event_id,
                    user_id=user_id,
                )
            )
            if not registration or registration.team_id is None:
                raise InvalidStateError("Вы не состоите в этой команде")
            if registration.team_id != team.id:
                raise InvalidStateError("Вы не состоите в этой команде")

            event = await self.uow.events.find_one_or_none(id=team.event_id)
            if not event:
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )
            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            team_with_members = await self.uow.teams.get_by_id_with_members(team.id)
            if not team_with_members:
                raise EntityNotFoundError(f"Команда с ID {team.id} не найдена")

            remaining_members = [
                member
                for member in team_with_members.members
                if member.user_id != user_id
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
                    key=lambda member: (
                        member.joined_team_at
                        or datetime.max.replace(tzinfo=timezone.utc)
                    ),
                )
                await self.uow.teams.update(
                    team.id, {"captain_id": new_captain.user_id}
                )

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
                raise EntityNotFoundError(
                    f"Мероприятие с ID {team.event_id} не найдено"
                )
            await self._sync_event_state(event)
            self._ensure_registration_phase(event)

            if team.captain_id != actor_user_id:
                raise PermissionDeniedError(
                    "Только капитан команды может исключать участников"
                )
            if member_user_id == actor_user_id:
                raise InvalidStateError("Капитан не может исключить сам себя")

            target_registration = (
                await self.uow.registrations.get_by_event_and_user_for_update(
                    event_id=event.id,
                    user_id=member_user_id,
                )
            )
            if not target_registration or target_registration.team_id != team.id:
                raise InvalidStateError("Пользователь не состоит в этой команде")

            team_with_members = await self.uow.teams.get_by_id_with_members(team.id)
            if not team_with_members:
                raise EntityNotFoundError(f"Команда с ID {team.id} не найдена")

            remaining_members = [
                member
                for member in team_with_members.members
                if member.user_id != member_user_id
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
