"""Pydantic-схемы для команд (Team)."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.enums import ParticipantSpecialization


# =====================================================================
# Схемы участников команды
# =====================================================================


class TeamMemberRead(BaseModel):
    """Схема участника команды для отображения в составе команды."""

    user_id: uuid.UUID
    full_name: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    is_captain: bool = False
    specializations: List[ParticipantSpecialization] = []
    skills: List[str] = []
    telegram_username: Optional[str] = None
    joined_team_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# Базовые схемы команд
# =====================================================================


class TeamBase(BaseModel):
    """Базовые поля команды."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Название команды (например, 'Drill Flex')",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Краткое описание идеи проекта или кого ищет команда",
    )
    max_members: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Желаемый размер команды, указанный капитаном (в пределах правил хакатона)",
    )
    needed_roles: List[ParticipantSpecialization] = Field(
        default_factory=list,
        description="Специализации 'Ищем' строго из перечисления ParticipantSpecialization",
    )
    allow_auto_match: bool = Field(
        default=True,
        description="Разрешить добавление свободных участников алгоритмом автораспределения",
    )


class TeamCreate(TeamBase):
    """Схема создания новой команды внутри хакатона."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Drill Flex",
                "description": "Разрабатываем платформу умного подбора команд для хакатонов",
                "max_members": 5,
                "needed_roles": ["backend", "design"],
                "allow_auto_match": True,
            }
        }
    )


class TeamUpdate(BaseModel):
    """Схема обновления данных команды капитаном или организатором."""

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=150,
        description="Новое название команды",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Новое описание проекта или задач команды",
    )
    max_members: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Новый желаемый размер команды",
    )
    needed_roles: Optional[List[ParticipantSpecialization]] = Field(
        default=None,
        description="Обновленный список специализаций 'Ищем'",
    )
    allow_auto_match: Optional[bool] = Field(
        default=None,
        description="Обновленный флаг разрешения автораспределения",
    )


# =====================================================================
# Схемы чтения команд
# =====================================================================


class TeamRead(BaseModel):
    """Схема чтения информации о команде для каталога команд мероприятия."""

    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    description: Optional[str] = None
    captain_id: uuid.UUID
    max_members: int
    needed_roles: List[ParticipantSpecialization] = []
    existing_roles: List[ParticipantSpecialization] = []
    members_count: int = 0
    members: List[TeamMemberRead] = []
    allow_auto_match: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def transform_team_orm(cls, data: Any) -> Any:
        """Динамически формирует список участников, вычисляет existing_roles и members_count."""
        # Если data — словарь (например, уже сериализованные данные)
        if isinstance(data, dict):
            return data

        # Если data — объект ORM модели Team
        if hasattr(data, "members") and hasattr(data, "captain_id"):
            members_list: List[Dict[str, Any]] = []
            existing_roles_seen = set()
            existing_roles_list: List[str] = []

            for reg in getattr(data, "members", []):
                user = getattr(reg, "user", None)
                if user:
                    is_captain = reg.user_id == data.captain_id
                    user_specs = getattr(user, "specializations", []) or []
                    user_skills = getattr(user, "skills", []) or []

                    members_list.append(
                        {
                            "user_id": user.id,
                            "full_name": user.full_name,
                            "nickname": user.nickname,
                            "avatar_url": user.avatar_url,
                            "is_captain": is_captain,
                            "specializations": user_specs,
                            "skills": user_skills,
                            "telegram_username": user.telegram_username,
                            "joined_team_at": reg.joined_team_at,
                        }
                    )

                    # Собираем канонические специализации участников в 'Уже есть' (строго user_specs, без skills)
                    for tag in list(user_specs):
                        if tag and tag not in existing_roles_seen:
                            existing_roles_seen.add(tag)
                            existing_roles_list.append(tag)

            return {
                "id": data.id,
                "event_id": data.event_id,
                "name": data.name,
                "description": data.description,
                "captain_id": data.captain_id,
                "max_members": data.max_members,
                "needed_roles": data.needed_roles or [],
                "existing_roles": existing_roles_list,
                "members_count": len(members_list),
                "members": members_list,
                "allow_auto_match": data.allow_auto_match,
                "created_at": data.created_at,
                "invite_token": getattr(data, "invite_token", None),
            }

        return data


class TeamDetailRead(TeamRead):
    """Детальная схема команды (включает invite_token для участников и статус текущего пользователя)."""

    invite_token: Optional[str] = Field(
        default=None,
        description="Секретный токен для прямого приглашения (доступен участникам команды и организаторам)",
    )
    is_user_member: bool = Field(
        default=False,
        description="Состоит ли текущий авторизованный пользователь в этой команде",
    )
    is_user_captain: bool = Field(
        default=False,
        description="Является ли текущий авторизованный пользователь капитаном этой команды",
    )
