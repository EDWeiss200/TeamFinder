"""Модель пользователя системы."""

from datetime import datetime
from typing import Optional, List

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import BigInteger, Boolean, Enum as SQLEnum, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from database.database import Base
from models.enums import UserRole


class User(SQLAlchemyBaseUserTableUUID, Base):
    """Таблица пользователей платформы (совместима с fastapi-users)."""

    __tablename__ = "users"

    # Роль в системе
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role_enum", native_enum=False),
        default=UserRole.PARTICIPANT,
        nullable=False,
    )

    # Профиль участника
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    university: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    study_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    course: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Навыки и роли
    skills: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default="{}",
        nullable=False,
    )
    primary_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Социальные сети
    vk_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Интеграция с Telegram-ботом
    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True,
    )
    telegram_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_bind_token: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
    )
    is_bot_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Аудит
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
