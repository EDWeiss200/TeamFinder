"""Роутер для загрузки медиа-файлов."""

from fastapi import APIRouter, Depends, File, UploadFile

from api.dependencies import upload_service
from auth.auth import current_user
from models.user import User
from schemas.upload import ImageUploadResponse
from services.upload_services import UploadServices

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
)


@router.post(
    "/image",
    response_model=ImageUploadResponse,
    summary="Загрузка изображения (аватарка или баннер)",
)
async def upload_image(
    file: UploadFile = File(
        ..., description="Файл изображения (JPEG, PNG, WebP до 5 МБ)"
    ),
    user: User = Depends(current_user),
    service: UploadServices = Depends(upload_service),
):
    """Загружает изображение на сервер и возвращает URL для сохранения в профиле или хакатоне."""
    url = await service.save_image(file)
    return ImageUploadResponse(url=url)
