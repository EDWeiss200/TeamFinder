"""Pydantic-схемы для загрузки медиа-файлов."""

from pydantic import BaseModel, Field


class ImageUploadResponse(BaseModel):
    """Схема ответа после успешной загрузки изображения."""

    url: str = Field(
        ...,
        description="URL загруженного изображения для сохранения в профиле или мероприятии",
    )
