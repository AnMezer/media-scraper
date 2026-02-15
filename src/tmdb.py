from encodings import johab
import os
import pprint
import re
import time
from http import HTTPStatus
from logging import raiseExceptions
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
from src.main import is_nfo_file_exists
from src.utils.exceptions import (
    APIAnswerWrongDataError,
    APIConnectionError,
    MissingVariableError,
    NoContentError,
    NoYearError,
    NotFoundError
)
from src.utils.logger import setup_logger
from src.utils.validators import validate_types, check_request_status
from src.utils.helpers import (get_content,
                             get_content_name_year, send_message, is_nfo_file_exists)
from utils.exceptions import ALotOfContentError
from utils.helpers import get_clean_info, create_nfo, create_images, \
    get_main_cast, get_season_info

SPLITTERS = r'[_.()]'


logger_name = 'Media scraper'
logger = setup_logger(logger_name)
bot = TeleBot(token=TELEGRAM_BOT_TOKEN)


def main():
    while True:
        latest_error_msg = ''
        try:
            # Получаем список сериалов
            tv_shows_path = os.path.join(
                MEDIA_ROOT_PATH, TV_SHOWS_FOLDER)  # type: ignore
            tv_shows = [tv_show.name for tv_show in os.scandir(tv_shows_path)
                        if tv_show.is_dir]
            show = tv_shows[1]  # Временно работаем с одним сериалом
            show_path = os.path.join(tv_shows_path, show)
            # Если nfo-файла нет, создаем его.
            if not is_nfo_file_exists(show_path, 'tv_show', show):
                content_title, content_year = get_content_name_year(
                                                            show, 'tv_show')
                content = get_content(
                    content_title, content_year, 'tv_show', show_path)
                content = content[0]
                content_info, images = get_clean_info(content)
                create_images(images, show_path)
                main_cast = get_main_cast(
                    str(content_info['TMDB_id']), 'tv_show')

                for person in main_cast:
                    photo_path = os.path.join(show_path, '.actors')
                    #create_images({person['name'].replace(' ',
                    #                                       '_'): person[
                    #                                       'photo_url']}, photo_path)
                    content_info['actors'].append(person)


                # Получаем информацию о кол-ве сезонов сохраненных локально
                seasons_folders = [season.name for season in
                                 os.scandir(show_path)
                                 if season.is_dir() and re.search(
                        r'(\d{1,2})$', season.name)]

                # Собираем словарь {№_сезона: папка_сезона}
                seasons = {}
                for season_folder in seasons_folders:
                    match = re.search(r'(\d{1,2})', season_folder)
                    seeason_number = int(match.group(1)) # Нужно добавить проверку
                    seasons[seeason_number] = season_folder
                # Собираем информацию о сезоне
                for season_number in seasons:
                    season_info = get_season_info(
                        season_number, content_info['TMDB_id'],
                        content_info['title'])
                    season_path = os.path.join(
                        show_path, seasons[season_number])
                    season_files = [file.name for file in os.scandir(
                            season_path) if file.is_file()]
                    for file in season_files:
                        episode_name, ext = os.path.splitext(file)
                        if ext in VIDEO_EXT:
                            match = re.search(r'S(\d{1,2})E(\d{1,'
                                              r'2})', episode_name)
                            if match:
                                if not is_nfo_file_exists(season_path,
                                                    'episode',
                                                          episode_name):
                                    s_number = int(match.group(1))
                                    ep_number = int(match.group(2))
                                    create_nfo(season_info['episodes'][
                                                   ep_number],
                                               season_path, 'episode',
                                               episode_name)
                                    pprint.pprint(content_info)



                        #seasons[season_number] = season_info

                    #create_nfo(content_info, show_path, 'tv_show')

                    #get_season_info(1, content_info['TMDB_id'])
        except Exception as e:
            error_message = f'Сбой в работе программы:\n{e}'
            if error_message != latest_error_msg:
                try:
                    send_message(bot, error_message)
                    latest_error_msg = error_message
                except Exception:
                    logger.error('Ошибка при отправке сообщения')
        break

if __name__ == '__main__':
    main()