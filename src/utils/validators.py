from http import HTTPStatus
import inspect
from src.utils.exceptions import (
    BadRequestError,
    CheckCallerDataError,
    InternalAPIError,
    MissingVariableError,
    UnauthorisedError,
    RequestLimitExceededError,
    TooManyRequestsError,
    APIConnectionError,
    UnprocessableEntityError
)


def validate_types_from_annotation():
    """

    Returns:
        None: 
    """
    try:
        caller_frame = inspect.currentframe().f_back
        if not caller_frame:
            raise CheckCallerDataError(
                'Не удалось получить фрейм вызывающей функции')
        caller_name = caller_frame.f_code.co_name  # Получаем имя вызывающей функции
        caller_obj = caller_frame.f_globals.get(caller_name)  # Получаем объект вызывающей функции
        if not caller_obj:
            raise CheckCallerDataError(
                f'Не удалось получить объект функции {caller_name}')
        if not hasattr(caller_obj, '__annotations__'):
            raise CheckCallerDataError(
                f'У функции {caller_name} отсутствуют аннотации типов')

        # Получаем аннотацию типов вызывающей функции
        annotations: dict = caller_obj.__annotations__.copy()
        if 'return' in annotations:
            annotations.pop('return')

        # получаем аргументы вызывающей функции
        current_vars = caller_frame.f_locals

    except CheckCallerDataError:
        raise
    finally:
        if caller_frame is not None:
            del caller_frame

    missing_keys = []
    for key in annotations.keys():
        if key not in current_vars.keys():
            missing_keys.append(key)
    if missing_keys:
        raise MissingVariableError(
            f'При вызове функции {caller_name} не переданы'
            f'необходимые переменные {", ".join(missing_keys)}'
        )
    else:
        for var_name, expected_type in annotations.items():
            if expected_type == 'None':
                continue
            if isinstance(current_vars[var_name], expected_type):
                continue
            else:
                raise TypeError(
                    f'Для {var_name} ожидался {expected_type.__name__}, '
                    f'Получен {type(current_vars[var_name]).__name__}'
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
        case HTTPStatus.FORBIDDEN:
            raise UnauthorisedError('Ошибка авторизации, токен заблокирован')
        case HTTPStatus.TOO_MANY_REQUESTS:
            raise TooManyRequestsError()
        case (HTTPStatus.INTERNAL_SERVER_ERROR | HTTPStatus.BAD_GATEWAY
              | HTTPStatus.SERVICE_UNAVAILABLE | HTTPStatus.GATEWAY_TIMEOUT):
            raise InternalAPIError()
        case HTTPStatus.PAYMENT_REQUIRED:
            raise BadRequestError()
        case HTTPStatus.UNPROCESSABLE_ENTITY:
            raise UnprocessableEntityError()
        case HTTPStatus.OK | HTTPStatus.NOT_FOUND:
            pass
        case _:
            raise APIConnectionError(f'API вернул код: {status_code}')
