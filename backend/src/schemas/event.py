"""Pydantic-схемы для мероприятий и регистраций участников."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import EventFormat, EventStatus


# =====================================================================
# Схемы профиля участника внутри регистрации
# =====================================================================


class EventRegistrationUserRead(BaseModel):
    """Краткая информация о пользователе для каталога участников."""

    id: uuid.UUID
    full_name: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    university: Optional[str] = None
    study_group: Optional[str] = None
    course: Optional[int] = None
    bio: Optional[str] = None
    skills: List[str] = []
    primary_role: Optional[str] = None
    telegram_username: Optional[str] = None
    vk_url: Optional[str] = None
    github_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# Схемы регистрации на мероприятие (EventRegistration)
# =====================================================================


class EventRegistrationCreate(BaseModel):
    """Схема подачи заявки на регистрацию в мероприятии."""

    role_in_team: str = Field(
        ...,
        max_length=100,
        description="Желаемая роль участника на мероприятии (например: 'фронт', 'бэк', 'дизайн')",
    )
    custom_answers: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Ответы на специфичные вопросы анкеты конкретного хакатона",
    )


class EventRegistrationRead(BaseModel):
    """Схема чтения данных регистрации участника на мероприятии."""

    id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    team_id: Optional[uuid.UUID] = None
    role_in_team: str
    custom_answers: Optional[Dict[str, Any]] = None
    joined_team_at: Optional[datetime] = None
    registered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SoloParticipantRead(BaseModel):
    """Схема свободного участника без команды для каталога 'Пригласить участников'."""

    id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    team_id: Optional[uuid.UUID] = None
    role_in_team: str
    custom_answers: Optional[Dict[str, Any]] = None
    registered_at: datetime
    user: EventRegistrationUserRead

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# Схемы мероприятий (Event)
# =====================================================================


class EventBase(BaseModel):
    """Базовые поля мероприятия."""

    title: str = Field(..., max_length=255, description="Название мероприятия")
    short_description: str = Field(
        ..., max_length=500, description="Краткое описание для карточки"
    )
    description_md: str = Field(
        ..., description="Полное описание мероприятия в формате Markdown"
    )
    organizer_name: str = Field(
        ..., max_length=255, description="Отображаемое имя организатора"
    )
    format: EventFormat = Field(
        default=EventFormat.ONLINE, description="Формат проведения"
    )
    tags: List[str] = Field(
        default_factory=list, description="Теги тематики мероприятия"
    )
    banner_url: Optional[str] = Field(
        default=None, max_length=512, description="Ссылка на баннер"
    )
    theme_color: str = Field(
        default="#0044FF", max_length=7, description="HEX-цвет баннера"
    )
    is_public: bool = Field(
        default=True, description="Показывать ли в общем каталоге на главной странице"
    )
    is_featured: bool = Field(
        default=False, description="Выводить ли в верхний слайдер на главной странице"
    )
    min_team_size: int = Field(
        default=1, ge=1, description="Минимальный размер команды"
    )
    max_team_size: int = Field(
        default=5, ge=1, le=50, description="Максимальный размер команды"
    )
    registration_start: datetime = Field(
        ..., description="Дата и время начала регистрации"
    )
    registration_end: datetime = Field(
        ..., description="Дедлайн регистрации и формирования команд"
    )
    event_start: datetime = Field(..., description="Начало основной части мероприятия")
    submission_deadline: datetime = Field(..., description="Дедлайн загрузки решений")
    event_end: datetime = Field(..., description="Окончание мероприятия")
    custom_fields_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Схема дополнительных вопросов анкеты под конкретный хакатон",
    )


class EventCreate(EventBase):
    """Схема создания нового мероприятия организатором."""

    status: Optional[EventStatus] = Field(
        default=EventStatus.REGISTRATION,
        description="Начальный статус мероприятия",
    )


class EventUpdate(BaseModel):
    """Схема обновления мероприятия организатором."""

    title: Optional[str] = Field(default=None, max_length=255)
    short_description: Optional[str] = Field(default=None, max_length=500)
    description_md: Optional[str] = None
    organizer_name: Optional[str] = Field(default=None, max_length=255)
    status: Optional[EventStatus] = None
    format: Optional[EventFormat] = None
    tags: Optional[List[str]] = None
    banner_url: Optional[str] = Field(default=None, max_length=512)
    theme_color: Optional[str] = Field(default=None, max_length=7)
    is_public: Optional[bool] = None
    is_featured: Optional[bool] = None
    min_team_size: Optional[int] = Field(default=None, ge=1)
    max_team_size: Optional[int] = Field(default=None, ge=1, le=50)
    registration_start: Optional[datetime] = None
    registration_end: Optional[datetime] = None
    event_start: Optional[datetime] = None
    submission_deadline: Optional[datetime] = None
    event_end: Optional[datetime] = None
    custom_fields_schema: Optional[Dict[str, Any]] = None


class EventRead(BaseModel):
    """Схема чтения информации о мероприятии для каталога на главной странице."""

    id: uuid.UUID
    title: str
    short_description: str
    organizer_name: str
    organizer_id: uuid.UUID
    status: EventStatus
    format: EventFormat
    tags: List[str]
    banner_url: Optional[str] = None
    theme_color: str
    is_public: bool
    is_featured: bool
    invite_code: str
    min_team_size: int
    max_team_size: int
    registration_start: datetime
    registration_end: datetime
    event_start: datetime
    submission_deadline: datetime
    event_end: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventDetailRead(EventRead):
    """Схема детальной страницы мероприятия (включает Markdown-описание и регистрацию текущего пользователя)."""

    description_md: str
    custom_fields_schema: Optional[Dict[str, Any]] = None
    my_registration: Optional[EventRegistrationRead] = None


class UserEventItemRead(BaseModel):
    """Схема мероприятия в списке личных событий пользователя (GET /users/me/events)."""

    event: EventRead
    registration: EventRegistrationRead

    model_config = ConfigDict(from_attributes=True)
