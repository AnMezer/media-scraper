import os
import pprint
import re
import time
from http import HTTPStatus
from unittest import result
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring
from cachetools.func import ttl_cache
from datetime import datetime

import requests
from requests.exceptions import RequestException
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException

from config.settings import (
    ENDPOINT_DATA_BY_FILM_ID,
    ENDPOINT_SEARCH_BY_KEYWORDS,
    ENDPOINT_STAFF_BY_FILM_ID,
    FILM_INFO_STRUCTURE,
    MAX_ACTORS,
    MEDIA_ROOT_PATH,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    VIDEO_EXT,
    X_API_KEY,
    YEAR_STAMP,
    GET_ID_CACHE_SIZE,
    GET_ID_TTL,
    DAY_LIMIT,
    SECOND_LIMIT,
    MOVIES_FOLDER,
    CARTOONS_FOLDER,
    TV_SHOWS_FOLDER
)
from .utils.exceptions import (
    APIAnswerWrongDataError,
    APIConnectionError,
    MissingVariableError,
    NoFilmsError,
    NoYearError,
    NotFoundError
)
from .utils.logger import setup_logger
from .utils.validators import validate_types, check_request_status

SPLITTERS = r'[_.()]'


logger_name = f'{__name__}'
logger = setup_logger(logger_name)
bot = TeleBot(token=TELEGRAM_BOT_TOKEN)


def main():
    while True:
        try:
            pass
        except Exception as e:
            error_message = f'Сбой в работе программы:\n{e}'
            if error_message != latest_error_msg:
                try:
                    send_message(bot, error_message)
                    latest_error_msg = error_message
                except Exception:
                    logger.error('Ошибка при отправке сообщения')
        time.sleep(10)


if __name__ == '__main__':
    main()