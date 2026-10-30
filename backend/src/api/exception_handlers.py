"""Глобальные обработчики доменных ошибок для FastAPI."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from utils.exceptions import (
    AlreadyInTeamError,
    DeadlinePassedError,
    DomainError,
    EntityNotFoundError,
    InvalidStateError,
    PermissionDeniedError,
    TeamIsFullError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрация обработчиков исключений доменной логики в приложении FastAPI."""

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message},
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message},
        )

    @app.exception_handler(TeamIsFullError)
    async def team_is_full_handler(request: Request, exc: TeamIsFullError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message},
        )

    @app.exception_handler(AlreadyInTeamError)
    async def already_in_team_handler(request: Request, exc: AlreadyInTeamError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message},
        )

    @app.exception_handler(DeadlinePassedError)
    async def deadline_passed_handler(request: Request, exc: DeadlinePassedError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message},
        )

    @app.exception_handler(InvalidStateError)
    async def invalid_state_handler(request: Request, exc: InvalidStateError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message},
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message},
        )
