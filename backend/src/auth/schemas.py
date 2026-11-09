"""Pydantic-схемы для аутентификации и профиля пользователя."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi_users import schemas
from pydantic import BaseModel, ConfigDict, Field

from models.enums import ParticipantSpecialization, UserRole


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Схема чтения профиля пользователя."""

    role: UserRole
    full_name: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    university: Optional[str] = None
    study_group: Optional[str] = None
    course: Optional[int] = None
    bio: Optional[str] = None
    skills: List[str] = []
    specializations: List[ParticipantSpecialization] = []
    vk_url: Optional[str] = None
    github_url: Optional[str] = None
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    is_bot_active: bool = False
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserCreate(schemas.BaseUserCreate):
    """Схема регистрации нового пользователя."""

    full_name: str
    nickname: Optional[str] = None
    university: Optional[str] = None
    study_group: Optional[str] = None
    course: Optional[int] = None
    skills: List[str] = []
    specializations: List[ParticipantSpecialization] = []


class UserUpdate(BaseModel):
    """Схема редактирования профиля текущего пользователя."""

    full_name: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    university: Optional[str] = None
    study_group: Optional[str] = None
    course: Optional[int] = None
    bio: Optional[str] = None
    skills: Optional[List[str]] = None
    specializations: Optional[List[ParticipantSpecialization]] = None
    vk_url: Optional[str] = None
    github_url: Optional[str] = None


class UserPasswordChange(BaseModel):
    """Схема безопасной смены пароля текущего пользователя."""

    old_password: str = Field(
        ..., description="Текущий пароль для подтверждения личности"
    )
    new_password: str = Field(
        ..., min_length=8, description="Новый пароль (минимум 8 символов)"
    )
