"""Кастомные доменные исключения платформы."""


class DomainError(Exception):
    """Базовое доменное исключение."""

    def __init__(self, message: str = "Произошла ошибка доменной логики"):
        self.message = message
        super().__init__(self.message)


class EntityNotFoundError(DomainError):
    """Сущность не найдена в базе данных."""

    def __init__(self, message: str = "Запрашиваемый ресурс не найден"):
        super().__init__(message)


class PermissionDeniedError(DomainError):
    """Отказано в доступе."""

    def __init__(self, message: str = "Недостаточно прав для выполнения операции"):
        super().__init__(message)


class TeamIsFullError(DomainError):
    """Команда уже заполнена."""

    def __init__(self, message: str = "В команде больше нет свободных мест"):
        super().__init__(message)


class AlreadyInTeamError(DomainError):
    """Участник уже состоит в команде на данном мероприятии."""

    def __init__(self, message: str = "Вы уже состоите в команде на этом мероприятии"):
        super().__init__(message)


class DeadlinePassedError(DomainError):
    """Дедлайн операции истек."""

    def __init__(self, message: str = "Срок выполнения данной операции истек"):
        super().__init__(message)


class InvalidStateError(DomainError):
    """Недопустимый статус сущности или неверное состояние."""

    def __init__(self, message: str = "Недопустимое состояние для выполнения операции"):
        super().__init__(message)


class UnprocessableEntityError(InvalidStateError):
    """Доменная ошибка валидации входных данных, соответствующая HTTP 422."""

    def __init__(self, message: str = "Невозможно обработать переданные данные"):
        super().__init__(message)


class IncompleteTeamError(DomainError):
    """Команда не набрала минимально необходимое количество участников."""

    def __init__(
        self,
        message: str = "Команда не набрала минимальное количество участников по регламенту мероприятия",
    ):
        super().__init__(message)

        
class RegistrationClosedError(InvalidStateError):
    """Регистрация на мероприятие закрыта (соответствует HTTP 409 Conflict)."""

    def __init__(
        self,
        message: str = "Операция доступна только во время фазы регистрации мероприятия",
    ):
        super().__init__(message)