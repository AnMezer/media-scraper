def validate_types(**kwargs):
    """Проверяет, что переданные значения соответствуют ожидаемым типам.

    kwargs: Пары вида var_name = (value< expected_type)
    """
    for name, (value, expected_type) in kwargs.items():
        if value is None or not isinstance(value, expected_type):
            raise TypeError(
                f'Для {name} ожидался {expected_type.__name__}, '
                f'Получен {type(value.__name__)}'
            )
