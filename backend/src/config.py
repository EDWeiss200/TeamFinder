"""Конфигурация приложения."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Ищем .env рядом с config.py (backend/src/.env) или в корне backend/
current_dir = Path(__file__).resolve().parent
load_dotenv(current_dir / ".env")
load_dotenv(current_dir.parent / ".env")
load_dotenv()

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "postgres")
DB_NAME = os.environ.get("DB_NAME", "teamtinder")
DB_PORT = os.environ.get("DB_PORT", "5432")

SECRET_AUTH = os.environ.get("SECRET_AUTH", "DEV_SECRET_AUTH_KEY_1234567890")
SECRET_USER_MANAGER = os.environ.get("SECRET_USER_MANAGER", "DEV_SECRET_USER_MANAGER_KEY_1234567890")

# Настройки Cookie: для локальной разработки без HTTPS устанавливается False
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "False").lower() in ("true", "1", "t")

# Токен Telegram-бота
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "TeamFinderBot")

# Разрешенные CORS-домены
FRONTEND_URLS = os.environ.get(
    "FRONTEND_URLS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
).split(",")

DATABASE_URL_CONFIG = (
    f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
