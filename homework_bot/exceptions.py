class ResponseStatusError(Exception):
    """Ошибка ответа сервера."""


class MissingTokensError(Exception):
    """Исключение для отсутствия необходимых переменных окружения."""
