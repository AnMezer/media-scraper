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
from src.utils.helpers import (get_content,
                             get_content_name_year, send_message, is_nfo_file_exists)
from utils.exceptions import ALotOfContentError
from utils.helpers import get_clean_info, create_nfo, create_image, \
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
            for show in tv_shows:
                show_path = os.path.join(tv_shows_path, show)

                # Если корневого nfo-файла нет, обрабатываем папку
                if not is_nfo_file_exists(show_path, 'tv_show', show):

                    #----------------------------------------------------------
                    # Получаем информацию о кол-ве сезонов сохраненных локально
                    seasons_folders = [season.name for season in
                                       os.scandir(show_path)
                                       if season.is_dir() and re.search(
                                                    r'(\d{1,2})$', season.name)]

                    # Собираем словарь {№_сезона: папка_сезона}
                    seasons_local = {}
                    for season_folder in seasons_folders:
                        match = re.search(r'(\d{1,2})', season_folder)
                        seeason_number = int(match.group(1))  # Нужно добавить проверку
                        seasons_local[seeason_number] = season_folder
                    #----------------------------------------------------------

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
                        actors_path = os.path.join(show_path, '.actors')
                        person_name = person['name'].replace(' ', '_')
                        create_image(person_name, person['photo_url'], actors_path)
                        content['actors'].append(person)
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
                        create_image(image_name, content[key], show_path)
                    create_nfo(content, show_path, 'tv_show')

                    # Обрабатываем сезоны
                    for s_num, s_data in content['seasons'].items():
                        # Создаем постеры сезонов
                        s_number = (
                            f'0{s_num}' if len(str(s_num)) < 2 else str(s_num))
                        image_name = f'season{s_number}-poster'
                        create_image(
                                 image_name, s_data['poster_path'], show_path)

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
                                                 season_path, 'episode',
                                                 file_name):
                                            poster_name = f'{file_name}-thumb'
                                            create_nfo(
                                                content['seasons'][s_num][
                                                'episodes'][
                                                           episode_num],
                                                season_path, 'episode',
                                                file_name)
                                            create_image(poster_name, content['seasons'][s_num][
                                                'episodes'][
                                                           episode_num][
                                                'episode_poster'], season_path)

                    #----------------------------------------------------------


                    # Собираем информацию о сезоне
                    # for season_number in seasons:
                    #     season_info = get_season_info(
                    #         season_number, content['id'],
                    #         content['title'])
                    #     season_path = os.path.join(
                    #         show_path, seasons[season_number])
                    #     season_files = [file.name for file in os.scandir(
                    #             season_path) if file.is_file()]
                    #     for file in season_files:
                    #         episode_name, ext = os.path.splitext(file)
                    #         if ext in VIDEO_EXT:
                    #             match = re.search(r'S(\d{1,2})E(\d{1,'
                    #                               r'2})', episode_name)
                    #             if match:
                    #                 if not is_nfo_file_exists(season_path,
                    #                                     'episode',
                    #                                           episode_name):
                    #                     s_number = int(match.group(1))
                    #                     ep_number = int(match.group(2))
                    #                     create_nfo(season_info['episodes'][
                    #                                    ep_number],
                    #                                season_path, 'episode',
                    #                                episode_name)
                    #
                    #
                    #
                    #     for season in content['seasons']:
                    #         season_number = season['season_number']
                    #         if season_number in seasons:
                    #             if len(str(season_number)) < 2:
                    #                 season_number = f'0{season_number}'
                    #             poster_name = f'season{season_number}-poster'
                    #             poster_url = f'{TMDB_IMAGES}{season['poster_path']}'
                    #             create_images({poster_name: poster_url}, show_path)
                    #
                    #     create_nfo(content, show_path, 'tv_show')

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