from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.event_router import router as event_router
from api.exception_handlers import register_exception_handlers
from api.team_router import router as team_router
from api.upload_router import router as upload_router
from api.user_router import router as user_router
from auth.auth import auth_backend, bearer_backend, fastapi_users
from auth.schemas import UserCreate, UserRead
from config import FRONTEND_URLS

app = FastAPI(
    title="TeamFinder API",
    description="Платформа автоматизации хакатонов, формирования команд и умного матчинга",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Монтирование директории статики для загружаемых медиа (аватарки, баннеры)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

# Роутер загрузки изображений
app.include_router(
    upload_router,
    prefix="/api/v1",
)

# Роутер мероприятий и каталога
app.include_router(
    event_router,
    prefix="/api/v1",
)

# Роутер управления командами
app.include_router(
    team_router,
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
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
