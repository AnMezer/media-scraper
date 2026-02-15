from http import HTTPStatus
from inspect import stack
import pprint
import re
from urllib import request
#from xml.etree.ElementTree import Element, SubElement
from lxml import etree

import requests
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from requests.exceptions import RequestException
import logging
import os

from config.settings import TELEGRAM_CHAT_ID, TMDB_GET_SHOW, TMDB_SEARCH_SHOW, \
    TMDB_TOKEN, YEAR_STAMP, VIDEO_EXT, TV_SHOW_INFO_STRUCTURE, TMDB_IMAGES, \
    TMDB_SHOW_CREDITS, TMDB_GET_SEASON, SEASON_INFO_STRUCTURE, \
    EPISODE_INFO_STRUCTURE
from src.main import SPLITTERS
from src.utils.exceptions import APIAnswerWrongDataError, APIConnectionError, \
    NoContentError, NoYearError, ScraperError
from src.utils.validators import check_request_status, validate_types, validate_types_from_annotation
from utils.exceptions import NfoCreateError

logger = logging.getLogger(f'Media scraper.{__name__}')


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
        return False
    logger.info('Сообщение успешно отправлено в Telegram.')
    return True


def is_nfo_file_exists(
        path: str, content_type: str, content_name: str) -> bool:
    """Проверяет наличие nfo-файла

    Args:
        path: Путь к папке с nfo файлом
        content_type: Тип контента(tv_show или movie)
        content_name: Название контента,
            - для сериалов имя корневой папки сериала.
            - для фильмов имя фидеофайла без расширения


    Returns:
        True, есди nfo-файл существует, иначе False
    """

    validate_types_from_annotation()
    if content_type == 'tv_show':
        nfo_file_name = 'tvshow.nfo'
    else:
        nfo_file_name = f'{content_name}.nfo'
    if nfo_file_name in [file.name for file in os.scandir(path)
                         if file.is_file()]:
        return True
    return False


def get_content_name_year(
        raw_name: str, content_type: str) -> tuple[str, str | None]:
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
    validate_types_from_annotation()
    if content_type == 'movie':
        match = re.search(YEAR_STAMP, raw_name)
        if match:
            year = match.group()
            raw_title = raw_name[:match.start()]
        else:
            raise NoYearError(
                f'У {raw_name} год выпуска не найден.\n'
                f'Проверьте имя файла/папки.')
    else:
        raw_title = raw_name
        year = None
    title = re.sub(SPLITTERS, ' ', raw_title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title, year


def get_content_by_id(id: int, content_type: str):
    """Получение данных о сериале по id"""
    validate_types_from_annotation()
    if content_type == 'tv_show':
        url = f'{TMDB_GET_SHOW}/{id}'
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'language': 'ru-Ru'}
                      }

    # Проверка статуса ответа API
    try:
        request_content = requests.get(**request_params)
    except RequestException as e:
        error_msg = (
            f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(error_msg)
    status_code = request_content.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None

    content: dict = request_content.json()
    validate_types(content=(content, dict))

    # Проверка наличия нужного ключа в ответе
    missing_keys = []
    for key in ('name', 'id', 'seasons', 'number_of_seasons'):
        if key not in content:
            missing_keys.append(key)
    if missing_keys:
        msg = f'Ключи: {", ".join(missing_keys)} отсутствует в ответе API'
        raise APIAnswerWrongDataError(msg)
    return content


def eliminate_uncertainty(
        uncertainty_content_ids: list, path: str) -> list[dict]:
    """
    Из нескольких id сериалов выбирает наиболее подходящий, возвращает
    информацию о нем, если однозначно определить не удалось,
    будет возвращена информация обо всех подходящих сериалах.
    Args:
        uncertainty_content_ids: Список id
        path: Путь к папке с сериалом

    Returns: Список словарей с информацией о сериалах

    """
    validate_types_from_annotation()
    # Получаем информацию о кол-ве сезонов сохраненных локально
    seasons_local = [season.name for season in os.scandir(path)
                     if season.is_dir() and re.search(r'(\d{1,2})$',
                                                      season.name)]
    # Получаем информацию о сериалах - кандидатах
    candidates = []
    for show_id in uncertainty_content_ids:
        raw_candidate = get_content_by_id(show_id, content_type='tv_show')
        # Если у кандидата сезонов столько же или больше, чем локально,
        # добавляем его
        if raw_candidate['number_of_seasons'] >= len(seasons_local):
            candidates.append(raw_candidate)

        # Если кандидатов > 1, проверяем кол-во серий в сезонах на соответствие
        if len(candidates) > 1:

            # Получаем словарь {<№ сезона>: <кол-во серий>}
            # Из локальных данных
            seasons_local_data = {}
            raw_candidates = candidates.copy()
            candidates = []
            for season_num in range(1, len(seasons_local) + 1):
                for folder_name in seasons_local:
                    match = re.search(r'(\d+)$', folder_name)
                    if int(match.group(1)) == season_num:
                        season_path = os.path.join(path, folder_name)
                        series = 0
                        for file in os.scandir(season_path):
                            if file.is_file() and file.name.endswith(VIDEO_EXT):
                                series += 1
                        seasons_local_data[season_num] = series

            # Получаем словарь {<№ сезона>: <кол-во серий>} у кандидата
            for candidate in raw_candidates:
                seasons = candidate['seasons']
                seasons_api_data = {season['season_number']: season[
                    'episode_count'] for season in seasons}

                # Проверяем совпадение локальных данных с данными в API:
                match = True
                for season_num, episode_count in seasons_local_data.items():
                    if seasons_api_data.get(season_num) != episode_count:
                        match = False
                        break
                if match:
                    candidates.append(candidate)
    return candidates

def get_content(
        content_title: str, content_year: str | None,
        content_type: str, path: str) -> list | None:
    """
    Возвращает информацию о фильме/сериале.
    Args:
        content_title: Название фильма/сериала
        content_year: Год выпуска (только для фильмов)
        content_type: movie или tv_show
        path: Путь к папке с фильмом/сериалом

    Returns:
        - Список словарей с информацией о контенте
        - None если ничего не найдено
    """
    validate_types_from_annotation()
    if content_type == 'tv_show':
        url = TMDB_SEARCH_SHOW
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'query': content_title,
                                 'language': 'ru-Ru',
                                 'year': {content_year if content_year
                                          else None}}
                      }
    # Проверка статуса ответа API
    try:
        request_search = requests.get(**request_params)
    except RequestException as e:
        error_msg = (
            f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(error_msg)
    status_code = request_search.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None

    request_data: dict = request_search.json()
    validate_types(request_data=(request_data, dict))

    # Проверка наличия нужного ключа в ответе
    if 'results' not in request_data:
        msg = 'Ключ results отсутствует в ответе API'
        raise APIAnswerWrongDataError(msg)

    results = request_data.get('results')
    if results is None:
        return None
    if len(results) == 0:
        raise NoContentError()

    # Если кандидат один, берем его id
    if len(results) == 1:

        # Проверка наличия нужного ключа в ответе
        if 'id' not in results[0]:
            msg = 'Ключ id отсутствует в выдаче API'
            raise APIAnswerWrongDataError(msg)

        # Проверка id на корректность
        content_id = results[0]['id']
        try:
            content_id = int(content_id)
        except (KeyError, ValueError):
            error_msg = f'Некорректный id в ответе API: {content_id}'
            raise APIAnswerWrongDataError(error_msg)

        content = get_content_by_id(results[0]['id'], content_type)
        if content is None:
            return None
        return [content,]

    # Если кандидатов несколько, получаем список с их id
    if len(results) > 1:
        uncertainty_content_ids = []
        for result in results:
            if 'id' not in result:
                continue
            try:
                content_id = result['id']
                content_id = int(content_id)
            except (KeyError, ValueError):
                continue
            uncertainty_content_ids.append(content_id)

        # Отфильтровываем лишних и получаем инфо об оставшихся
        candidates = eliminate_uncertainty(uncertainty_content_ids, path)
        return candidates
    raise ScraperError('Ошибка выполнения функции get_content')

def get_clean_info(raw_info: dict):
    """
    Разделяет исходную информацию на два словаря: данные и изображения
    Args:
        raw_info: Словарь с сырыми данными

    Returns:
        content_info - данные для сохранения в nfo файл
        images - ссылки на изображения
    """
    images = {}
    content_info = {}
    validate_types_from_annotation()
    for key, value in TV_SHOW_INFO_STRUCTURE.items():
        clean_value = raw_info.get(value)
        if value in ('poster_path', 'backdrop_path'):
            images[key] = f'{TMDB_IMAGES}/{clean_value}'
        else:
            content_info[key] = clean_value
    content_info['actors'] = []
    return content_info, images

def create_nfo(
        content_info: dict, path: str, content_type: str,
        file_name: str | None = None):
    """
    Создает nfo файл.
    Args:
        content_info: Словарь с данными для сохранения в файле.
        path: папка для создания файла.
        content_type: movie или tv_show.
        file_name: имя nfo файла, только для фильмов.

    Returns:

    """
    validate_types_from_annotation()
    keys_to_skip = ('photo_url', 'id', 'seasons')
    try:
        if content_type == 'tv_show':
            file_name = 'tvshow.nfo'
            root_name = 'tvshow'
        else:
            file_name = f'{file_name}.nfo'
            root_name = 'movie'
        nfo_path = os.path.join(path, file_name)
        root = etree.Element(root_name)
        for tag, tag_value in content_info.items():
            if tag == 'genres':
                for genre in tag_value:
                    tag = etree.SubElement(root, 'genre')
                    tag.text = str(genre['name'])
            elif tag == 'countries':
                for country in tag_value:
                    tag = etree.SubElement(root, 'country')
                    tag.text = str(country['name'])
            elif tag == 'actors':
                for actor in tag_value:
                    actor_elem = etree.SubElement(root, 'actor')
                    for key, value in actor.items():
                        if key not in keys_to_skip:
                            sub_tag = etree.SubElement(actor_elem, key)
                            sub_tag.text = str(value)
            else:
                tag = etree.SubElement(root, tag)
                tag.text = str(tag_value)
        rough_xml = etree.tostring(root, encoding='utf-8',
                                   xml_declaration=True, pretty_print=True)
        final_xml = rough_xml.decode('utf-8')
        with open(nfo_path, 'w', encoding='utf-8') as f:
            f.write(final_xml)
    except Exception as e:
        raise NfoCreateError(e)

def create_images(images: dict, path):
    """
    Загружает и создает изображения.
    Args:
        images: Словарь {название файла: ссылка}
        path: Адрес папки для сохранения

    Returns:

    """
    validate_types_from_annotation()
    os.makedirs(path, exist_ok=True)
    for image_type, url in images.items():
        image = requests.get(url=url)
        file_name = f'{image_type}.jpg'
        file_path = os.path.join(path, file_name)
        with open(file_path, 'wb') as f:
            f.write(image.content)

def get_main_cast(content_id: str, content_type: str):
    """
    Возвращает информацию о главных актерах
    Args:
        content_id: id фильма/сериала
        content_type: movie или tv_show

    Returns:
        Список словарей с информацией об актерах.
    """
    validate_types_from_annotation()
    if content_type == 'tv_show':
        url = TMDB_SHOW_CREDITS.format(content_id)
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {
                                 'language': 'ru-Ru',}}

    # Проверка статуса ответа API
    try:
        request_cast = requests.get(**request_params)
    except RequestException as e:
        error_msg = (
            f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(error_msg)
    status_code = request_cast.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None

    request_data: dict = request_cast.json()
    cast = []
    for person in request_data['cast']:
        person_info = {}
        person_info['name'] = person.get('name')
        person_info['role'] = person.get('character')
        person_info['order'] = person.get('order')
        person_info['id'] = person.get('id')
        raw_url = person.get('profile_path')
        if raw_url is not None:
            person_info['photo_url'] = f'{TMDB_IMAGES}{raw_url}'
        full_info = True
        for tag in person_info:
            if tag is None:
                full_info = False
        if full_info:
            cast.append(person_info)
        else:
            continue
    return cast

def get_season_info(season_num, id,):
    """
    Возвращает словарь с информацией о сезоне.
    Args:
        season_num: Номер сезона
        id: id сериала

    Returns:
        Словарь с общей информацией о сезоне и списком с информацией о сериях.
    """
    validate_types_from_annotation()
    request_params = {'url': TMDB_GET_SEASON.format(id, season_num),
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'language': 'ru-Ru'}
                      }

    # Проверка статуса ответа API
    try:
        request_season = requests.get(**request_params)
    except RequestException as e:
        error_msg = (
            f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(error_msg)
    status_code = request_season.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None

    request_data: dict = request_season.json()
    validate_types(request_data=(request_data, dict))
    episodes = request_data['episodes']
    season_info = {}

    for tag, tag_info in SEASON_INFO_STRUCTURE.items():
        if tag != 'episodes':
            season_info[tag] = request_data.get(tag_info)
        season_info['episodes'] = []

    for episode in episodes:
        episode_info = {}
        episode_info[episode['episode_number']] = {}
        for tag, tag_info in EPISODE_INFO_STRUCTURE.items():
            if tag == 'showtitle':
                episode_info[episode['episode_number']]['showtitle'] = ''
            else:
                episode_info[episode['episode_number']][tag] = episode.get(tag_info)
        season_info['episodes'].append(episode_info)
    return season_info