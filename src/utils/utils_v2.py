import os
import pprint
import re
from dataclasses import fields, asdict
from http import HTTPStatus
from itertools import chain
from xml.etree.ElementTree import SubElement

import requests
from PIL import Image, UnidentifiedImageError
from lxml import etree
from lxml.html.defs import tags
from requests import JSONDecodeError, RequestException
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException

from config.settings import SPLITTERS, YEAR_STAMP, TMDB_SEARCH_SHOW, \
    TMDB_SEARCH_MOVIE, TMDB_TOKEN, TMDB_GET_SHOW, TV_SHOW_INFO_STRUCTURE, \
    TMDB_GET_MOVIE, FILM_INFO_STRUCTURE, TMDB_IMAGES, TMDB_SHOW_CREDITS, \
    TMDB_MOVIE_CREDITS, MAX_ACTORS, TELEGRAM_CHAT_ID
#from tmdb_v2 import Movie
from utils.exceptions import APIConnectionError, ResponseProcessingError, \
    APIAnswerWrongDataError, NoContentError, CreateImageError, SendMessageError
from utils.validators import check_request_status

def send_message(bot: TeleBot, message: str) -> bool:
    """Отправляет пользователю сообщение в Telegram.

    Args:
        bot: Telegram-бот
        message: Отправляемое сообщение.

    Raises:
        MessageSendError: В случае ошибки при отправке.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except (ApiTelegramException, RequestException):
        raise SendMessageError()
    #logger.info('Сообщение успешно отправлено в Telegram.')

def get_content_name_year(
        raw_name: str, content_type: str) -> tuple[str | None, str | None]:
    """Извлекает название и год выпуска из "сырого" имени файла/папки.

    Для фильмов год обязателен и должен присутствовать в имени в формате (ГГГГ)
    Для сериалов год игнорируется (всегда возвращается None)

    Args:
        raw_name:
            - для сериалов - имя корневой папки
            - для фильмов - имя видеофайла без расширения
        content_type: Тип контента(tv_show или movie)

    Raises:
        NoYearError: Если для фильма не найден год.

    Returns:
        Кортеж из двух элементов:
            - Очищенное название (без разделителей и лишних пробелов).
            - Год выпуска (ГГГГ) (для фильмов) или None (для сериалов).
    """
    if content_type == 'movie':
        match = re.search(YEAR_STAMP, raw_name)
        if match:
            year = int(match.group())
            raw_title = raw_name[:match.start()]
        else:
            return None, None
    else:
        raw_title = raw_name
        year = None
    title = re.sub(SPLITTERS, ' ', raw_title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title, year

def is_nfo_file_exists(
        path: str, content_type: str, content_name: str) -> bool:
    """Проверяет наличие nfo-файла

    Args:
        path: Путь к папке с nfo файлом
        content_type: Тип контента(tv_show, episode или movie)
        content_name: Название контента,
            - для сериалов имя корневой папки сериала.
            - для фильмов имя видеофайла без расширения


    Returns:
        True, если nfo-файл существует, иначе False
    """
    if content_type == 'tv_show':
        nfo_file_name = 'tvshow.nfo'
    else:
        nfo_file_name = f'{content_name}.nfo'
    if nfo_file_name in [file.name for file in os.scandir(path)
                         if file.is_file()]:
        return True
    return False

def fetch_data(data_type: str, **request_params) -> dict | bytes| None:
    """
    Отправляет GET запрос к API, выполняет первичное преобразование ответа
    в зависимости от параметра type.
    Args:
        data_type: Необходимый тип данных (json или content).
        **request_params: Параметры запроса.
    Raises:
        RequestException: Ошибка при получении ответа.
        UnauthorisedError: Ошибка авторизации.
        RequestLimitExceededError: Превышен дневной или общий лимит на запросы к API.
        TooManyRequestsError: Превышен секундный лимит на запросы к API.
        APIConnectionError: Код ответа отличен от ожидаемых.
        JSONDecodeError: Не удалось распарсить ответ API
    Returns:
        Ответ API приведенный к нужному типу.
        None, если 404.
    """
    expected_data_types = ('content', 'json')
    if data_type not in expected_data_types:
        raise ValueError(f'Неподдерживаемый тип данных. '
                         f'Ожидаются {", ".join(expected_data_types)}')
    try:
        response = requests.get(**request_params)
    except RequestException as e:
        error_msg = (
            f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(error_msg)
    status_code = response.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None
    try:
        match data_type:
            case 'content':
                return response.content
            case 'json':
                return response.json()
    except JSONDecodeError as e:
        raise ResponseProcessingError(f'Ошибка обработки ответа API {e}')

def get_content_id(
        content_title: str, content_year: str | None,
        content_type: str, path: str = None) -> set:
    """
    Возвращает информацию о фильме/сериале.
    Args:
        content_title: Название фильма/сериала
        content_year: Год выпуска (только для фильмов)
        content_type: movie или tv_show
        path: Путь к папке с фильмом/сериалом

    Returns:
        - Словарь с информацией о контенте
        - None если ничего не найдено
    """

    if content_type == 'tv_show':
        url = TMDB_SEARCH_SHOW
    else:
        url = TMDB_SEARCH_MOVIE
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'query': content_title,
                                 'language': 'ru-Ru',
                                 'primary_release_year': content_year
                                                    if content_year else None}
                      }
    content = fetch_data('json', **request_params)

    # Проверка наличия нужного ключа в ответе
    if 'results' not in content:
        msg = 'Ключ results отсутствует в ответе API'
        raise APIAnswerWrongDataError(msg)

    results = content.get('results')
    if len(results) == 0:
        raise NoContentError()

    # Если кандидат один, берем его id
    # TODO: Тут можно упростить
    if len(results) == 1:
        result = results[0]

        if 'id' not in result:
            msg = 'Ключ id отсутствует в выдаче API'
            raise APIAnswerWrongDataError(msg)

        # Проверка id на корректность
        content_id = result.get('id')
        try:
            content_id = int(content_id)
        except (KeyError, ValueError):
            error_msg = f'Некорректный id в ответе API: {content_id}'
            raise APIAnswerWrongDataError(error_msg)

        return (content_id,)
    else:
        candidate_popularity = {}
        for idx, candidate in enumerate(results):
            candidate_popularity[idx] = candidate['popularity']
        max_popularity = max(candidate_popularity.values())
        for idx, popularity in candidate_popularity.copy().items():
          if popularity == 0 or max_popularity / popularity > 3:
              candidate_popularity.pop(idx)
        ids = set(results[idx]['id'] for idx in candidate_popularity)
        return ids

def get_content_by_id(id: int, content_type: str):
    """Получение данных о фильме/сериале"""
    if content_type == 'tv_show':
        url = f'{TMDB_GET_SHOW}/{id}'
        expected_keys = list(TV_SHOW_INFO_STRUCTURE.values())
    else:
        url = f'{TMDB_GET_MOVIE}/{id}'
        expected_keys = list(FILM_INFO_STRUCTURE.values())
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'language': 'ru-Ru'}
                      }
    content = fetch_data('json', **request_params)

    return content if content else None

def img_valid(img_path):
    try:
        with Image.open(img_path) as img:
            img.verify()
            return True
    except (IOError, SyntaxError, UnidentifiedImageError, ValueError):
        return False

def create_image(image_name: str, url_path: str, path:str):
    """
    Загружает и создает изображения.
    Args:
        image_name: Имя, с которым следует создать файл
        url_path: последний сегмент ссылки на изображения (/3851982849458.jpg)
        path: Адрес папки для сохранения

    Returns:

    """
    os.makedirs(path, exist_ok=True)
    url = f'{TMDB_IMAGES}{url_path}'
    image = fetch_data('content', url=url)
    file_name = f'{image_name}'
    file_path = os.path.join(path, file_name)
    try:
        with open(file_path, 'wb') as f:
            f.write(image)
    except (PermissionError, OSError, IsADirectoryError) as e:
        raise CreateImageError(
            f'Ошибка при сохранении изображения {file_path}: {e}')

def get_main_cast(content_id: int, content_type: str):
    """
    Возвращает информацию о главных актерах
    Args:
        content_id: id фильма/сериала
        content_type: movie или tv_show

    Returns:
        Список словарей с информацией об актерах.
    """
    if content_type == 'tv_show':
        url = TMDB_SHOW_CREDITS.format(content_id)
    else:
        url = TMDB_MOVIE_CREDITS.format(content_id)
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {
                                 'language': 'ru-Ru',}}
    full_staff = fetch_data('json', **request_params)

    actors = {}
    directors = {}
    actor_order = 0
    director_order = 0
    # TODO: добавить проверку наличия ключей
    for person in chain(full_staff.get('cast', []), full_staff.get('crew', [])):

        person_name = person.get('name')
        person_photo_url = person.get('profile_path')
        person_role = person.get('character')
        person_job = person.get('job')

        if person_photo_url and person_photo_url.startswith('/'):
            if person_job == 'Director':
                directors[director_order] = {'name': person_name,
                                             'photo_url': person_photo_url}

                director_order += 1
            elif person_role:
                if len(actors) < MAX_ACTORS:
                    actors[actor_order] = {'name': person_name,
                                 'photo_url': person_photo_url,
                                 'role': person_role,
                                 }

                    actor_order += 1
    return actors, directors

def create_nfo(obj):
    content_type = obj.content_type
    match content_type:
        case 'movie':
            root_name = 'movie'
            file_name = f'{obj.file_name}.nfo'
        case 'tv_show':
            root_name = 'tv_show'
            file_name = 'tv_show.nfo'
        case 'episode':
            root_name = 'episodedetails'
            file_name = f'{obj.file_name}.nfo'
    nfo_path = os.path.join(obj.path, file_name)
    root = etree.Element(root_name)
    tags = fields(obj)
    for tag in tags:
        tag_type = tag.metadata.get('tag_type', None)
        if tag_type:
            tag_name = tag.name
            tag_value = getattr(obj, tag_name)
            match tag_type:
                case 'single':
                    elem = etree.SubElement(root, tag_name)
                    elem.text = str(tag_value)
                case 'multi':
                    tag_name = tag_name[:-1]
                    for item in tag_value:
                        name = item.get('name', None)
                        if name:
                            elem = etree.SubElement(root, tag_name)
                            elem.text = str(name)
                case 'actors':
                    tag_name = tag_name[:-1]
                    for order, actor_obj in tag_value.items():
                        tag_actor = etree.SubElement(root, tag_name)
                        actor_tags = fields(actor_obj)
                        for actor_tag in actor_tags:
                            field_type = actor_tag.metadata.get('field_type',
                                                                None)
                            if field_type != 'image':
                                elem = etree.SubElement(tag_actor,
                                                        actor_tag.name)
                                text = getattr(actor_obj, actor_tag.name)
                                elem.text = str(text)
                        elem = etree.SubElement(tag_actor, 'order')
                        elem.text = str(order)
                case 'directors':
                    tag_name = tag_name[:-1]
                    for director in tag_value.values():
                        elem = etree.SubElement(root, tag_name)
                        elem.text = str(director.name)

    rough_xml = etree.tostring(root, encoding='utf-8',
                               xml_declaration=True, pretty_print=True)
    final_xml = rough_xml.decode('utf-8')
    with open(nfo_path, 'w', encoding='utf-8') as f:
        f.write(final_xml)

def save_candidates_nfo(path: str, candidates_ids: set, content_type: str):
    for id in candidates_ids:
        # TODO: Раббить для разного типа контента
        candidate = get_content_by_id(id, 'movie')


