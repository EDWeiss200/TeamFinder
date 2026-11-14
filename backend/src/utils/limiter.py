"""Общий limiter для rate limiting роутеров."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_user_or_ip_key(request: Request) -> str:
    """Ключ лимитера: для авторизованных запросов — по пользователю/токену, иначе по IP."""
    # 1. Проверяем переопределение current_user в тестах
    for dep, provider in request.app.dependency_overrides.items():
        if getattr(dep, "__name__", "") == "current_user" or "current_user" in str(dep):
            try:
                user = provider()
                if hasattr(user, "id"):
                    return f"user:{user.id}"
            except Exception:
                pass
    # 2. Проверяем заголовок Authorization или сессионную Cookie
    auth_header = request.headers.get("Authorization")
    if auth_header:
        return f"auth:{auth_header}"
    session_cookie = request.cookies.get("teamtinder_session")
    if session_cookie:
        return f"cookie:{session_cookie}"
    return get_remote_address(request)


limiter = Limiter(key_func=get_user_or_ip_key)
ip_limiter = Limiter(key_func=get_remote_address)