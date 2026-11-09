"""CLI-команда для создания первого администратора/организатора платформы."""

import argparse
import asyncio
import sys

from sqlalchemy import select

from auth.auth import password_helper
from database.database import async_session_maker
from models.enums import UserRole
from models.user import User


async def create_superuser(
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.ADMIN,
) -> None:
    """Создает супер-администратора или организатора в базе данных."""
    async with async_session_maker() as session:
        # Проверяем, существует ли уже пользователь с таким email
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"Ошибка: Пользователь с email '{email}' уже существует.")
            sys.exit(1)

        hashed_password = password_helper.hash(password)
        new_user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            is_active=True,
            is_superuser=True,
            is_verified=True,
            skills=[],
            specializations=[],
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        print(f"Супер-администратор успешно создан: ID={new_user.id}, Email={new_user.email}, Роль={new_user.role.value}")


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        description="Создание первого администратора платформы TeamFinder"
    )
    parser.add_argument(
        "--email",
        type=str,
        required=True,
        help="Email адрес администратора",
    )
    parser.add_argument(
        "--password",
        type=str,
        required=True,
        help="Пароль администратора (минимум 8 символов)",
    )
    parser.add_argument(
        "--full-name",
        type=str,
        default="Главный Администратор",
        help="ФИО администратора",
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=[r.value for r in UserRole],
        default=UserRole.ADMIN.value,
        help="Роль в системе (admin или organizer)",
    )

    args = parser.parse_args()

    if len(args.password) < 8:
        print("Ошибка: Пароль должен содержать не менее 8 символов.")
        sys.exit(1)

    asyncio.run(
        create_superuser(
            email=args.email,
            password=args.password,
            full_name=args.full_name,
            role=UserRole(args.role),
        )
    )


if __name__ == "__main__":
    main()
