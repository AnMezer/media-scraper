

class ScraperError(Exception):
    """Ошибка скрипта"""


class CheckCallerDataError(ScraperError):
    def __str__(self) -> str:
        return 'Ошибка получения информации о вызывающей функции'


class MissingVariableError(ScraperError):
    """Отсутствуют необходимые переменные"""


class NoYearError(ScraperError):
    """В названии файла отсутствует год"""


class APIConnectionError(ScraperError):
    """Ошибка получения ответа от API"""


class UnauthorisedError(ScraperError):
    """Пустой или неправильный токен"""


class TooManyRequestsError(ScraperError):
    def __str__(self) -> str:
        return 'Слишком частые запросы к API'


class InternalAPIError(ScraperError):
    def __str__(self) -> str:
        return 'Внутренняя ошибка API'


class BadRequestError(ScraperError):
    def __str__(self) -> str:
        return 'Ошибка формата запроса'


class UnprocessableEntityError(ScraperError):
    def __str__(self) -> str:
        return 'API не может обработать запрос'


class APIAnswerWrongDataError(ScraperError):
    """Ответ API отличается от ожидаемого"""


class NoContentError(ScraperError):
    def __str__(self) -> str:
        return 'Ответ API пуст'




    





class RequestLimitExceededError(Exception):
    """Превышен дневной или общий лимит на запросы к API"""


class NotFoundError(Exception):
    """В API результатов не найдено"""
