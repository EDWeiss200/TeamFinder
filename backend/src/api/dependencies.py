"""Фабрики зависимостей и проверки прав доступа."""

from fastapi import Depends
from auth.auth import current_user
from models.enums import UserRole
from models.user import User
from services.user_services import UserServices
from utils.exceptions import PermissionDeniedError
from utils.uow import IUnitOfWork, UnitOfWork


def get_uow() -> IUnitOfWork:
    """Провайдер Unit of Work."""
    return UnitOfWork()


def user_service(uow: IUnitOfWork = Depends(get_uow)) -> UserServices:
    """Провайдер сервиса пользователей с инъекцией Unit of Work."""
    return UserServices(uow)


async def require_organizer(user: User = Depends(current_user)) -> User:
    """Проверка прав: пользователь должен обладать ролью ORGANIZER или ADMIN (или быть superuser)."""
    if user.role not in (UserRole.ORGANIZER, UserRole.ADMIN) and not user.is_superuser:
        raise PermissionDeniedError("Доступ разрешен только организаторам и администраторам")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    """Проверка прав: пользователь должен обладать ролью ADMIN (или быть superuser)."""
    if user.role != UserRole.ADMIN and not user.is_superuser:
        raise PermissionDeniedError("Доступ разрешен только супер-администраторам")
    return user
