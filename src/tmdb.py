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
from telebot.util import content_type_media

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

def process_seasons(content: 'Content', to_create: 'ToCreate'):
    # Добавляем постеры сезонов в загрузки
    for season_num, season_data in (
            content.data['seasons'].items()):
        s_num = (f'0{season_num}' if len(str(season_num)) < 2
                 else str(season_num))
        image_name = f'season{s_num}-poster'
        to_create.images.append({
            'image_name': image_name,
            'url_path': season_data['poster_path'],
            'path': content.path})

        # Получаем список серий
        season_path = os.path.join(
            content.path, content.seasons_folders[season_num])
        files = [file.name for file in os.scandir(season_path)
                 if file.is_file()]
        for file in files:
            file_name, ext = os.path.splitext(file)
            if ext in VIDEO_EXT:
                match = re.search(
                    r'S(\d{1,2})E(\d{1,2})', file_name)
                if match:
                    episode_num = int(match.group(2))
                    if not is_nfo_file_exists(
                            season_path, 'episode', file_name):
                        episode_data = \
                        content.data['seasons'][season_num]['episodes'][
                            episode_num]
                        poster_name = f'{file_name}-thumb'
                        to_create.nfos.append({
                            'content': episode_data,
                            'path': season_path,
                            'content_type': 'episode',
                            'file_name': file_name
                        })
                        to_create.images.append({
                            'image_name': poster_name,
                            'url_path': episode_data['episode_poster'],
                            'path': season_path})

class Content:
    def __init__(self, content_folder_name: str, content_type: str,
                 title: str =None, year: str = None):
        """

        Args:
            content_folder_name: Корневая папка сериала или папка с фильмом
            content_type: movie, cartoon или tv_show
            title: Название (после очистки)
            year: Год выпуска (после очистки)
        """

        self.folder_name = content_folder_name
        self.title = title if title else None
        self.year = year if year else None
        self.content_type = content_type
        self.data = {}

        if content_type == 'tv_show':
            self.path = os.path.join(
                os.path.join(
                    MEDIA_ROOT_PATH, TV_SHOWS_FOLDER), content_folder_name)
            self.seasons_folders = get_seasons_local_data(self.path)

        else:
            cont_type_folder = f'{content_type}s'
            self.path = os.path.join(
                os.path.join(
                    MEDIA_ROOT_PATH, cont_type_folder), content_folder_name)
            self.seasons_folders = None

    def need_nfo_processing(self):
        return not is_nfo_file_exists(
            self.path, self.content_type, self.folder_name)


class ToCreate:
    def __init__(self):
        self.images = []
        self.nfos = []

    def create(self):
        for nfo in self.nfos:
            create_nfo(**nfo)
        for image in self.images:
            create_image(**image)
        print(f'Создано: nfo - {len(self.nfos)}, images - {len(self.images)}')

def main():
    while True:
        latest_error_msg = ''
        try:
            to_create = ToCreate()
            for root_folder in (MOVIES_FOLDER, CARTOONS_FOLDER, TV_SHOWS_FOLDER):
                match root_folder:
                    case 'Cartoons' | 'Movies':
                        content_type = 'movie'
                    case 'Serials':
                        content_type = 'tv_show'
                if root_folder != TV_SHOWS_FOLDER:
                    continue
                    movies_path = os.path.join(MEDIA_ROOT_PATH, parent_folder)
                    movies = [folder.name for folder in os.scandir(
                                            movies_path) if folder.is_dir()]
                    for movie in movies:
                        content_path = os.path.join(movies_path, movie)
                        content = Content(content_path, content_type)
                        if content.need_nfo_processing():
                            content.title, content.year = (
                                get_content_name_year(movie, content_type))
                            print(content.title, content.year)
                    continue
                # Получаем список произведений
                tv_shows_path = os.path.join(MEDIA_ROOT_PATH, root_folder)
                tv_shows_folders = [tv_show.name for tv_show in os.scandir(
                                                tv_shows_path)
                                    if tv_show.is_dir()]
                for tv_show_folder in tv_shows_folders:
                    content = Content(tv_show_folder, content_type, '', '')
                    if content.need_nfo_processing():
                        content.title, content.year = get_content_name_year(
                            content.folder_name, content.content_type)
                        raw_content = get_content(
                            content.title, content.year, content_type, content.path)
                        content.data = get_clean_info(
                            raw_content, content_type,list(content.seasons_folders.keys()))
                        to_create.nfos.append({'content': content.data,
                                               'path': content.path,
                                               'content_type': content_type,
                                               'file_name': None})
                        # Добавляем актеров в content, добавляем фото для загрузки
                        staff = get_main_cast(
                            str(content.data['TMDB_id']), content_type)
                        content.data['actors'] = []
                        for person in staff:
                            content.data['actors'].append(person)
                            actors_path = os.path.join(content.path, '.actors')
                            person_name = person['name'].replace(' ', '_')
                            to_create.images.append({
                                                    'image_name': person_name,
                                                    'url_path': person['photo_url'],
                                                    'path': actors_path})

                        # Добавляем информацию о сериях в сезоны
                        seasons = content.data['seasons']
                        for season_num, season_data in seasons.items():
                            episodes = seasons[season_num]['episodes'] = {}
                            raw_episodes_data = get_season_info(
                                                season_num, content.data['TMDB_id'])
                            for raw_episode_data in raw_episodes_data.values():
                                episode_data = get_clean_info(
                                                raw_episode_data, 'episode', None)
                                episode_data['showtitle'] = content.data['title']
                                episodes[episode_data['episode']] = episode_data

                        # Добавляем главные постер и задник в загрузки
                        for key in ('poster_path', 'backdrop_path'):
                            image_name = IMAGES_MAP.get(key)
                            to_create.images.append({
                                'image_name': image_name,
                                'url_path': content.data[key],
                                'path': content.path})

                        process_seasons(content, to_create)

                to_create.create()

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