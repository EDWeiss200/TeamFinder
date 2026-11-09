"""Общие Pydantic-схемы платформы."""

import math
from typing import Generic, List, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Универсальная схема ответа для пагинированных списков."""

    items: List[T] = Field(..., description="Элементы текущей страницы")
    total: int = Field(..., ge=0, description="Общее количество записей")
    page: int = Field(..., ge=1, description="Номер текущей страницы (начиная с 1)")
    size: int = Field(..., ge=1, description="Размер страницы (лимит элементов)")
    pages: int = Field(..., ge=0, description="Общее количество страниц")

    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        page: int,
        size: int,
    ) -> "PaginatedResponse[T]":
        """Фабричный метод вычисления количества страниц и формирования схемы."""
        pages = math.ceil(total / size) if size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=pages,
        )
