"""Сервисный слой для работы с евентами"""

import secrets
import uuid
from typing import Optional

from auth.auth import password_helper
from auth.schemas import UserUpdate
from config import BOT_USERNAME
from models.user import User
from utils.exceptions import EntityNotFoundError, InvalidStateError
from utils.uow import IUnitOfWork


class EventServices:

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow