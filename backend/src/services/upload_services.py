"""Сервис для валидации и сохранения загружаемых медиа-файлов."""

import hashlib
import secrets
from pathlib import Path
from typing import Set

from fastapi import UploadFile
from PIL import Image

from utils.exceptions import InvalidStateError

# Разрешенные MIME-типы и расширения
ALLOWED_IMAGE_TYPES: Set[str] = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 Мегабайт

# Директория загрузки статики: backend/static/uploads/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"


class UploadServices:
    """Сервис обработки медиа-файлов."""

    def __init__(self, upload_dir: Path = UPLOAD_DIR):
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_image(self, file: UploadFile) -> str:
        """Валидирует и сохраняет загруженное изображение.

        Возвращает относительный URL для доступа к файлу.
        """
        # 1. Проверка Content-Type
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise InvalidStateError(
                f"Неподдерживаемый формат файла '{file.content_type}'. "
                "Разрешены только JPEG, PNG и WebP."
            )

        # 2. Чтение содержимого с проверкой размера
        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE_BYTES:
            raise InvalidStateError(
                f"Превышен допустимый размер файла ({len(contents) / (1024 * 1024):.1f} МБ). "
                "Максимальный размер: 5 МБ."
            )

        # 3. Валидация целостности картинки через Pillow
        try:
            import io

            image = Image.open(io.BytesIO(contents))
            image.verify()
        except Exception:
            raise InvalidStateError(
                "Файл поврежден или не является валидным изображением"
            )

        # 4. Формирование уникального имени файла
        ext = (
            file.filename.split(".")[-1].lower()
            if file.filename and "." in file.filename
            else "webp"
        )
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "webp"

        file_hash = hashlib.sha256(contents).hexdigest()[:16]
        unique_name = f"{file_hash}_{secrets.token_hex(4)}.{ext}"
        destination_path = self.upload_dir / unique_name

        # 5. Запись на диск
        with open(destination_path, "wb") as f:
            f.write(contents)

        return f"/static/uploads/{unique_name}"
