# Файл: backend/tests/test_upload_services.py
"""Модульные тесты для UploadServices (валидация и сохранение изображений)."""

import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from services.upload_services import MAX_IMAGE_SIZE_BYTES, UploadServices
from utils.exceptions import InvalidStateError


def make_upload_file(content: bytes, filename: str, content_type: str) -> UploadFile:
    """Вспомогательная фабрика UploadFile с заданным MIME-типом."""
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def generate_valid_image_bytes(fmt: str = "PNG") -> bytes:
    """Генерирует валидное изображение 10x10 пикселей в памяти через Pillow."""
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(buf, format=fmt)
    return buf.getvalue()


async def test_save_image_valid_png(tmp_path: Path):
    """Валидный PNG-файл успешно проходит проверку Pillow и сохраняется на диск."""
    service = UploadServices(upload_dir=tmp_path)
    img_bytes = generate_valid_image_bytes("PNG")
    upload = make_upload_file(img_bytes, "avatar.png", "image/png")

    url = await service.save_image(upload)

    assert url.startswith("/static/uploads/")
    assert url.endswith(".png")
    saved_filename = url.split("/")[-1]
    assert (tmp_path / saved_filename).exists()


async def test_save_image_rejects_unsupported_mime_type(tmp_path: Path):
    """Файлы с неподдерживаемым Content-Type (например, SVG или PDF) отклоняются."""
    service = UploadServices(upload_dir=tmp_path)
    upload = make_upload_file(b"fake pdf", "doc.pdf", "application/pdf")

    with pytest.raises(InvalidStateError, match="Неподдерживаемый формат"):
        await service.save_image(upload)


async def test_save_image_rejects_file_over_5mb(tmp_path: Path):
    """Файл размером более 5 МБ отклоняется с InvalidStateError."""
    service = UploadServices(upload_dir=tmp_path)
    huge_bytes = b"0" * (MAX_IMAGE_SIZE_BYTES + 1024)
    upload = make_upload_file(huge_bytes, "huge.jpg", "image/jpeg")

    with pytest.raises(InvalidStateError, match="Превышен допустимый размер"):
        await service.save_image(upload)


async def test_save_image_rejects_corrupted_image_bytes(tmp_path: Path):
    """Если под видом image/png загружены битые байты (не картинка), Pillow блокирует файл."""
    service = UploadServices(upload_dir=tmp_path)
    upload = make_upload_file(b"not_an_image_at_all", "hack.png", "image/png")

    with pytest.raises(InvalidStateError, match="Файл поврежден"):
        await service.save_image(upload)
