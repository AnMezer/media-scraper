import logging
import sys


def setup_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Функция настройки логгера.

    Args:
        name (str): Имя логгера.
        level (int, optional): Уровень логгирования. По умолчанию logging.DEBUG

    Returns:
        logging.Logger: Объект логгера
    """
    time_format = '%Y-%m-%d %H:%M'
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s]: %(message)s',
        datefmt=time_format
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
