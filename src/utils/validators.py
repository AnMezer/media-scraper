from http import HTTPStatus
from src.utils.exceptions import (
    UnauthorisedError,
    RequestLimitExceededError,
    TooManyRequestsError,
    APIConnectionError
)


def validate_types(**kwargs):
    """Проверяет, что переданные значения соответствуют ожидаемым типам.

    kwargs: Пары вида var_name = (value, expected_type)
    """
    for name, (value, expected_type) in kwargs.items():
        if value is None or not isinstance(value, expected_type):
            raise TypeError(
                f'Для {name} ожидался {expected_type.__name__}, '
                f'Получен {type(value).__name__}'
            )


def check_request_status(status_code: int):
    """Проверяет статус ответа API.

    Args:
        status_code: Статус-код ответа API.

    Raises:
        UnauthorisedError: Ошибка авторизации.
        RequestLimitExceededError: Превышен дневной или общий лимит на запросы к API.
        TooManyRequestsError: Превышен секундный лимит на запросы к API.
        APIConnectionError: Код ответа отличен от ожидаемых.
    """
    match status_code:
        case HTTPStatus.UNAUTHORIZED:
            raise UnauthorisedError('Ошибка авторизации, проверьте токен API')
        case HTTPStatus.PAYMENT_REQUIRED:
            raise RequestLimitExceededError(
                'Превышен дневной или общий лимит на запросы к API')
        case HTTPStatus.TOO_MANY_REQUESTS:
            raise TooManyRequestsError(
                'Превышен секундный лимит на запросы к API')
        case HTTPStatus.OK:
            pass
        case HTTPStatus.NOT_FOUND:
            pass
        case _:
            raise APIConnectionError(f'API вернул код: {status_code}')
