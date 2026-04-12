from dataclasses import dataclass, field
from email.policy import default
from encodings import johab
import os
import pprint
import re
import time
from fileinput import filename
from http import HTTPStatus
from logging import raiseExceptions
from unittest import result
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from PIL import Image
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
    TV_SHOWS_FOLDER, TMDB_IMAGES, IMAGES_MAP, TMDB_TOKEN, TMDB_SEARCH_MOVIE
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
from src.utils.utils import (get_content, fetch_data)
from src.utils.utils_v2 import (send_message,
                                get_content_name_year,
                                is_nfo_file_exists,
                                create_nfo)
from utils.exceptions import ALotOfContentError, MissingTagError
from utils.utils_v2 import (get_content_id, get_content_by_id, create_image,
                            get_main_cast, img_valid)

MSG_FILE_NOT_DEFINED = (
    'Не удалось идентифицировать видео-файл, он отсутствует или их несколько. '
    'Проверьте папку: {folder}')
MSG_PARSER_ERROR = (
    'Не удалось распознать название фильма или год выпуска, '
    'проверьте имя файла: {folder}/{file}')
MSG_MANY_CANDIDATES = (
    'При обработке {folder} найдено кандидатов: {quantity}.'
)
MSG_NO_ID_ERROR = (
    'Не удалось получить ID фильма: {folder}/{file}'
)

logger_name = 'Media scraper_v2'
logger = setup_logger(logger_name)
bot = TeleBot(token=TELEGRAM_BOT_TOKEN)

@dataclass
class Content:

    # Базовые данные (из файловой системы)
    folder: str
    path: str | None = field(default=None)

    # Одиночные тэги
    title: str = field(default=None, metadata={'tag_type': 'single'})
    originaltitle: str = field(default=None, metadata={'tag_type': 'single'})
    tagline: str = field(default=None, metadata={'tag_type': 'single'})
    premiered: str = field(default=None, metadata={'tag_type': 'single'})
    plot: str = field(default=None, metadata={'tag_type': 'single'})
    rating_themoviedb: float = field(default=None,
                                     metadata={'tag_type': 'single'})
    votes_themoviedb: int = field(default=None, metadata={'tag_type': 'single'})
    mpaa: str = field(default=None, metadata={'tag_type': 'single'})
    tmdb_id: int = field(default=None, metadata={'tag_type': 'single'})

    # Множественные тэги
    genres: dict = field(default_factory=dict, metadata={'tag_type': 'multi'})
    countries: dict = field(default_factory=dict,
                            metadata={'tag_type': 'multi'})
    studios: dict = field(default_factory=dict, metadata={'tag_type': 'multi'})
    actors: dict = field(default_factory=dict, metadata={'tag_type': 'actors'})
    directors: dict = field(default_factory=dict,
                            metadata={'tag_type': 'directors'})

    # Изображения
    poster_url: str = field(default=None, metadata={'img_type': 'poster'})
    fanart_url: str = field(default=None, metadata={'img_type': 'fanart'})

    # Технические
    candidates: set = field(default=None, metadata={'used': False})

    def create_posters(self):
        logger.info(f'Обработка постеров...')
        for image_type in ('poster', 'fanart'):
            img_name = f'{self.file_name}-{image_type}.jpg'
            img_path = os.path.join(self.path, img_name)

            need_create = False

            if os.path.isfile(img_path):
                logger.debug(
                    f'"{image_type}" существует, проверка целостности...')
                if img_valid(img_path):
                    logger.debug('Файл исправен.')
                else:
                    logger.warning(f'"{image_type}" поврежден.')
                    need_create = True
            else:
                logger.debug(f'"{image_type}" отсутствует.')
                need_create = True

            if need_create:
                logger.debug(f'Приступаю к созданию {img_name}...')
                create_image(img_name, self.poster_url, self.path)
                if img_valid(img_path):
                    logger.success(f'"{image_type}" успешно создан и '
                                   f'проверен.')
                    continue
                else:
                    logger.error(f'Ошибка при создании файла {img_name}')

    def __post_init__(self):

        if self.folder:
            self.path = os.path.join(
                MEDIA_ROOT_PATH, MOVIES_FOLDER, self.folder)

    class Meta:
        abstract = True

@dataclass
class Movie(Content):

    # Базовые данные (из файловой системы)
    file: str | None = field(default=None)
    raw_title: str | None = field(default=None)
    file_name: str | None = field(default=None)
    year: int | None = field(default=None)
    missing_tags: dict = field(
        default_factory=lambda: FILM_INFO_STRUCTURE.copy()
    )

    # Одиночные тэги
    runtime: int = field(default=None, metadata={'tag_type': 'single'})

    # Неиспользуемые:
    belongs_to_collection: dict = field(default_factory=dict,
                                        metadata={'used': False})

    content_type: str = field(default='movie')

    def __post_init__(self):
        super().__post_init__()

        self.file  = self.get_video_file()

        if self.file and self.path:
            self.raw_title, self.year = get_content_name_year(self.file,
                                                              self.content_type)

        if self.file:
            self.file_name, _ = os.path.splitext(self.file)

        if not self.premiered:
            self.premiered = f'{self.year}-01-01'


    def need_nfo_processing(self):
        """Проверяет необходимость создания nfo файла"""
        return not os.path.isfile(
            os.path.join(self.path, f'{self.file_name}.nfo'))

    def get_video_file(self):
        """Возвращает имя видео-файла
        None - если однозначно распознать не удалось
        """

        if self.path:
            files = [file.name for file in
                     os.scandir(self.path) if file.name.endswith(VIDEO_EXT)]
            if len(files) > 1:
                return None
            if not files:
                return None
            return files[0]
        return None

    def base_info_exists(self):
        """Проверяет наличие минимально необходимой информации о фильме"""
        if self.raw_title is None or self.year is None:
            error_msg = MSG_PARSER_ERROR.format(
                folder=self.folder, file=self.file)
            logger.error(error_msg)
            return False
        return True

    def get_tmdb_id(self):
        ids = get_content_id(self.raw_title, self.year, self.content_type)
        if len(ids) > 1:
            self.candidates = ids
        else:
            self.tmdb_id = next(iter(ids))

    def get_staff_info(self):
        actors, directors = get_main_cast(self.tmdb_id, self.content_type)

        for order, person_data in actors.items():
            person = Person(**person_data)
            self.actors[order] = person

        for order, person_data in directors.items():
            person = Person(**person_data)
            self.directors[order] = person

    def update_data(self, content: dict):
        missing_attrs = []
        for tag in FILM_INFO_STRUCTURE:
            if hasattr(self, tag):
                value = content.get(FILM_INFO_STRUCTURE[tag])
                setattr(self, tag, value)
                self.missing_tags.pop(tag)
            else:
                missing_attrs.append(f' {tag}: {FILM_INFO_STRUCTURE[tag]}')
        if missing_attrs:
            raise MissingTagError(f'У объекта отсутствуют атрибуты для пар: '
                                  f'{', '.join(missing_attrs)}')

    def create_photos(self):
        failed_images = []
        logger.info(f'Обработка фото актеров...')
        photos_path = os.path.join(self.path, '.actors')
        for actor in self.actors.values():
            img_name = f'{actor.name.replace(' ', '_')}.jpg'
            img_path = os.path.join(photos_path, img_name)
            if os.path.isfile(img_path):
                logger.debug(f'{img_name} уже существует')
                # TODO: добавить проверку валидности
            else:
                try:
                    create_image(img_name, actor.photo_url, photos_path)
                except Exception:
                    failed_images.append(img_name)
        if failed_images:
            logger.error(
                f'Ошибка при создании изображений: {", ".join(failed_images)}. '
                f'Папка: {photos_path}')
        else:
            logger.success(f'Фото актеров для {self.title} успешно обработаны.')

    def file_defined(self):
        if self.file is None:
            error_msg = MSG_FILE_NOT_DEFINED.format(folder=self.folder)
            logger.error(error_msg)
            return False
        return True

    def id_defined(self):
        if not self.tmdb_id and self.candidates:
            error_msg = MSG_MANY_CANDIDATES.format(
                folder=self.folder, quantity=len(self.candidates))
            logger.error(error_msg)
            return False
        if not self.tmdb_id and not self.candidates:
            error_msg = MSG_NO_ID_ERROR.format(
                folder=self.folder, file=self.file)
            logger.error(error_msg)
        return True

    def create_nfo(self):
        logger.info(f'Создание nfo файла...')
        try:
            create_nfo(self)
            logger.success(f'{self.file_name}.nfo создан.')
        except Exception:
            # TODO: Ловить исключения качественнее
            logger.error(f'Ошибка при создании {self.file_name}.nfo')

@dataclass
class TvShow(Content):

    def need_nfo_processing(self):
        return not os.path.isfile(os.path.join(
            MEDIA_ROOT_PATH, TV_SHOWS_FOLDER, self.folder, 'tvshow.nfo')
        )

    def __post_init__(self):
        super().__post_init__()


@dataclass
class Person:
    """Класс описывающий тэги актеров"""
    name: str
    photo_url: str = field(default=None, metadata={'field_type': 'image'})
    role: str = field(default=None)

def main():
    time_start = datetime.now()
    problem_items = []
    latest_error_msg = ''
    try:
        parent_path = os.path.join(MEDIA_ROOT_PATH, MOVIES_FOLDER)
        content_folders = [folder.name for folder in
                            os.scandir(parent_path) if folder.is_dir()]
        for folder in content_folders:
            try:
                if folder in problem_items:
                    continue
                movie = Movie(folder)
                if not movie.file_defined():
                    continue

                if movie.need_nfo_processing():
                    logger.debug('- ' * 30)
                    logger.debug(f'Обработка {movie.folder}.')

                    if not movie.base_info_exists():
                        problem_items.append(movie.folder)
                        continue

                    movie.get_tmdb_id()
                    if not movie.id_defined():
                        problem_items.append(movie.folder)
                        continue

                    content = get_content_by_id(movie.tmdb_id,
                                                movie.content_type)
                    if not content:
                        error_msg = (f'Не удалось получить данные о фильме '
                                     f'по ID {movie.raw_title}')
                        logger.error(error_msg)
                        latest_error_msg = error_msg
                        continue
                    # TODO: Нужно создавать nfo файл из того, что есть
                    movie.update_data(content)
                    movie.get_staff_info()
                    movie.create_posters()
                    movie.create_photos()
                    movie.create_nfo()

            except Exception as e:
                logger.exception(
                    f'Ошибка при обработке {movie.folder}: {e}')
                problem_items.append(movie.folder)
                continue


        work_time = datetime.now() - time_start
        if problem_items:
            logger.warning(
                f'Ошибка при обработке папок: {", ".join(problem_items)}')
        logger.info(f'Время выполнения {work_time}')

    except Exception as e:
        error_message = f'Сбой в работе программы: {type(e).__name__} {e}.'
        if error_message != latest_error_msg:
            try:
                logger.error(error_message)
                send_message(bot, error_message)
                latest_error_msg = error_message
                problem_items.append(movie.folder)
            except Exception:
                logger.error('Ошибка при отправке сообщения')



if __name__ == '__main__':
    main()
