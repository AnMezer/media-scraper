import logging
import sys

import colorlog


SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, 'SUCCESS')

def success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kws)

logging.Logger.success = success

def setup_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Функция настройки логгера.

    Args:
        name (str): Имя логгера.
        level (int, optional): Уровень логгирования. По умолчанию logging.DEBUG

    Returns:
        logging.Logger: Объект логгера
    """
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'white',
        'SUCCESS': 'bold_green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    }


    time_format = '%Y-%m-%d %H:%M'
    format = '%(log_color)s%(asctime)s - %(name)s - [%(levelname)s]: %(message)s'
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = colorlog.StreamHandler()
        formatter = colorlog.ColoredFormatter(
            format, datefmt=time_format, log_colors=log_colors
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
