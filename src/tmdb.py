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
    TV_SHOWS_FOLDER, TMDB_IMAGES, IMAGES_MAP
)
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
from src.utils.utils import (get_content,
                             get_content_name_year, send_message, is_nfo_file_exists)
from utils.exceptions import ALotOfContentError
from utils.utils import get_clean_info, create_nfo, create_image, \
    get_main_cast, get_season_info

SPLITTERS = r'[_.()]'


logger_name = 'Media scraper'
logger = setup_logger(logger_name)
bot = TeleBot(token=TELEGRAM_BOT_TOKEN)

def get_seasons_local_data(show_path: str) -> dict:
    """
    Собирает информацию о сезонах имеющихся в хранилище
    Args:
        show_path: Путь к папке с сериалом

    Returns:
        seasons_local: словарь {№_сезона: папка_сезона}
    """
    seasons_folders = [
        season.name for season in os.scandir(show_path)
        if season.is_dir() and re.search(r'(\d{1,2})$', season.name)]

    # Собираем словарь {№_сезона: папка_сезона}
    seasons_local = {}
    for season_folder in seasons_folders:
        match = re.search(r'(\d{1,2})', season_folder)
        seeason_number = int(match.group(1))
        seasons_local[seeason_number] = season_folder
    return seasons_local


def main():
    while True:
        latest_error_msg = ''
        try:
            # Получаем список сериалов
            tv_shows_path = os.path.join(
                MEDIA_ROOT_PATH, TV_SHOWS_FOLDER)  # type: ignore
            tv_shows = [tv_show.name for tv_show in os.scandir(tv_shows_path)
                        if tv_show.is_dir]
            for show in tv_shows:
                show_path = os.path.join(tv_shows_path, show)

                # Если корневого nfo-файла нет, обрабатываем папку
                if not is_nfo_file_exists(show_path, 'tv_show', show):
                    images_to_download = []
                    seasons_local = get_seasons_local_data(show_path)
                    content_title, content_year = get_content_name_year(
                                                                show, 'tv_show')

                    raw_content = get_content(
                        content_title, content_year, 'tv_show', show_path)
                    content = get_clean_info(raw_content, 'tv_show',
                                             list(seasons_local.keys()))
                    # Добавляем список актеров в content, сохраняем их фото
                    #----------------------------------------------------------
                    main_cast = get_main_cast(str(content['TMDB_id']),
                                              'tv_show')
                    content['actors'] = []
                    for person in main_cast:
                        content['actors'].append(person)
                        actors_path = os.path.join(show_path, '.actors')
                        person_name = person['name'].replace(' ', '_')
                        images_to_download.append({
                            'image_name': person_name,
                            'url_path': person['photo_url'],
                            'path': actors_path})
                    #----------------------------------------------------------

                    # Добавляем информацию о сериях в сезоны
                    for season_num, season_data in content['seasons'].items():
                        episodes = content['seasons'][season_num]['episodes'] = {}
                        raw_episodes_data = get_season_info(
                                                season_num, content['TMDB_id'])
                        for raw_ep_data in raw_episodes_data.values():
                            episode_data = get_clean_info(
                                                 raw_ep_data, 'episode', None)
                            episode_data['showtitle'] = content['title']
                            episodes[episode_data['episode']] = episode_data

                    #----------------------------------------------------------
                    # Создаем постер сериала, фон-задник и nfo для сериала
                    for key in ('poster_path', 'backdrop_path'):
                        image_name = IMAGES_MAP.get(key)
                        images_to_download.append({
                            'image_name': image_name,
                            'url_path': content[key],
                            'path': show_path})


                    # Обрабатываем сезоны
                    for s_num, s_data in content['seasons'].items():
                        # Создаем постеры сезонов
                        s_number = (
                            f'0{s_num}' if len(str(s_num)) < 2 else str(s_num))
                        image_name = f'season{s_number}-poster'
                        images_to_download.append({
                            'image_name': image_name,
                            'url_path': s_data['poster_path'],
                            'path': show_path})

                        # Получаем список серий
                        season_path = os.path.join(show_path, seasons_local[s_num])
                        files = [file.name for file in os.scandir(
                                                 season_path) if file.is_file()]
                        for file in files:
                            file_name, ext = os.path.splitext(file)
                            if ext in VIDEO_EXT:
                                     match = re.search(
                                         r'S(\d{1,2})E(\d{1,2})', file_name)
                                     if match:
                                         episode_num = int(match.group(2))
                                         if not is_nfo_file_exists(
                                                 season_path, 'episode', file_name):
                                            episode_data = content['seasons'][s_num]['episodes'][episode_num]
                                            poster_name = f'{file_name}-thumb'
                                            create_nfo(episode_data, season_path, 'episode', file_name)
                                            images_to_download.append({
                                                'image_name': poster_name,
                                                'url_path': episode_data['episode_poster'],
                                                'path': season_path})

                    create_nfo(content, show_path, 'tv_show')
                    for image in images_to_download:
                        create_image(**image)

        except Exception as e:
            error_message = f'Сбой в работе программы:\n{type(e).__name__} {e}'
            if error_message != latest_error_msg:
                try:
                    logger.error(error_message)
                    send_message(bot, error_message)
                    latest_error_msg = error_message
                except Exception:
                    logger.error('Ошибка при отправке сообщения')
        break

if __name__ == '__main__':
    main()