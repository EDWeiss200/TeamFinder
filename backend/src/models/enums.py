import enum


class UserRole(str, enum.Enum):
    """Роли пользователей в системе."""
    PARTICIPANT = "participant"
    ORGANIZER = "organizer"
    ADMIN = "admin"


class EventStatus(str, enum.Enum):
    """Статусы жизненного цикла мероприятия."""
    DRAFT = "draft"
    REGISTRATION = "registration"
    TEAM_LOCK = "team_lock"
    SUBMISSION = "submission"
    FINISHED = "finished"


class EventFormat(str, enum.Enum):
    """Формат проведения мероприятия."""
    OFFLINE = "offline"
    ONLINE = "online"
    HYBRID = "hybrid"


class TeamRequestStatus(str, enum.Enum):
    """Статусы заявок и приглашений в команду."""
    PENDING_CAPTAIN = "pending_captain"
    PENDING_USER = "pending_user"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class TeamRequestType(str, enum.Enum):
    """Тип заявки: отклик студента или приглашение капитана."""
    APPLICATION = "application"
    INVITE = "invite"
