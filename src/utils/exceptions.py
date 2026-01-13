

class DefaultError(Exception):
    """Ошибка скрипта"""


class MissingVariableError(Exception):
    """Отсутствуют необходимые переменные"""


class NoYearError(Exception):
    """В названии файла отсутствует год"""


class APIConnectionError(Exception):
    """Ошибка получения ответа от API"""


class APIAnswerWrongDataError(Exception):
    """Ответ API отличается от ожидаемого"""


class NoFilmsError(Exception):
    """В ответе API список films пуст"""


class UnauthorisedError(Exception):
    """Пустой или неправильный токен"""


class RequestLimitExceededError(Exception):
    """Превышен дневной или общий лимит на запросы к API"""


class TooManyRequestsError(Exception):
    """Превышен сукундный лимит на запросы к API"""


class NotFoundError(Exception):
    """В API результатов не найдено"""
