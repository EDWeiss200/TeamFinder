import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.exception_handlers import register_exception_handlers
from api.user_router import router as user_router
from auth.auth import auth_backend, bearer_backend, fastapi_users
from auth.schemas import UserCreate, UserRead
from config import FRONTEND_URLS

app = FastAPI(
    title="HackFlow API",
    description="Платформа автоматизации хакатонов, формирования команд и умного матчинга",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Настройка CORS для взаимодействия с фронтендом
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрация глобальных обработчиков доменных ошибок
register_exception_handlers(app)

# Роутеры аутентификации (Cookie-транспорт)
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/api/v1/auth/jwt",
    tags=["Auth"],
)

# Роутеры аутентификации (Bearer Token транспорт для мобильных устройств и тестов)
app.include_router(
    fastapi_users.get_auth_router(bearer_backend),
    prefix="/api/v1/auth/bearer",
    tags=["Auth"],
)

# Роутер регистрации новых пользователей
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/api/v1/auth",
    tags=["Auth"],
)

# Роутер пользователей и профилей
app.include_router(
    user_router,
    prefix="/api/v1",
)


@app.get("/", tags=["Root"])
async def root():
    """Корневой эндпоинт со ссылкой на документацию."""
    return {
        "message": "TeamFinder API is running",
        "docs_url": "/docs",
        "health_check": "/health",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Проверка жизнеспособности сервиса."""
    return {"status": "ok", "service": "TeamFinder API"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
