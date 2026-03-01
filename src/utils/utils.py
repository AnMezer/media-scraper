from http import HTTPStatus
from inspect import stack
import pprint
import re
from urllib import request
from urllib.parse import urljoin

#from xml.etree.ElementTree import Element, SubElement
from lxml import etree

import requests
from requests import Response, JSONDecodeError
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from requests.exceptions import RequestException
import logging
import os

from config.settings import TELEGRAM_CHAT_ID, TMDB_GET_SHOW, TMDB_SEARCH_SHOW, \
    TMDB_TOKEN, YEAR_STAMP, VIDEO_EXT, TV_SHOW_INFO_STRUCTURE, TMDB_IMAGES, \
    TMDB_SHOW_CREDITS, TMDB_GET_SEASON, SEASON_INFO_STRUCTURE, \
    EPISODE_INFO_STRUCTURE, IMAGES_MAP, FILM_INFO_STRUCTURE, IMAGES_KEYS, \
    TMDB_SEARCH_MOVIE, TMDB_GET_MOVIE, TMDB_MOVIE_CREDITS, MAX_ACTORS
from src.main import SPLITTERS
from src.utils.exceptions import APIAnswerWrongDataError, APIConnectionError, \
    NoContentError, NoYearError, ScraperError, ALotOfContentError, \
    ResponseProcessingError
from src.utils.validators import check_request_status, validate_types, validate_types_from_annotation
from utils.exceptions import NfoCreateError, CreateImageError

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
        expected_keys = list(TV_SHOW_INFO_STRUCTURE.values())
    else:
        url = f'{TMDB_GET_MOVIE}/{id}'
        expected_keys = list(FILM_INFO_STRUCTURE.values())
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'language': 'ru-Ru'}
                      }
    content = fetch_data('json', **request_params)
    validate_types(content=(content, dict))
    # Проверка наличия нужного ключа в ответе
    missing_keys = []
    for key in expected_keys:
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
                     if season.is_dir() and re.search(r'(\d{1,2})',
                                                      season.name)]
    candidates = []
    # Получаем информацию о сериалах - кандидатах
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
        content_type: str, path: str) -> dict | None:
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
    validate_types_from_annotation()

    if content_type == 'tv_show':
        url = TMDB_SEARCH_SHOW
    else:
        url = TMDB_SEARCH_MOVIE
    request_params = {'url': url,
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'query': content_title,
                                 'language': 'ru-Ru',
                                 'year': content_year if content_year
                                          else None}
                      }
    content = fetch_data('json', **request_params)

    validate_types(content=(content, dict))

    # Проверка наличия нужного ключа в ответе
    if 'results' not in content:
        msg = 'Ключ results отсутствует в ответе API'
        raise APIAnswerWrongDataError(msg)

    results = content.get('results')
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
        return content

    # Если кандидатов несколько, получаем список с их id
    if len(results) > 1:
        if content_type != 'tv_show':
            # TODO: добавить логику фильтрации лишних фильмов
            if content_title == 'Tomb Raider Лара Крофт':
                content = get_content_by_id(338970, content_type)
                return content
            elif content_title == 'Van Helsing':
                content = get_content_by_id(7131, content_type)
                return content
            elif content_title == 'In Time':
                content = get_content_by_id(49530, content_type)
                return content

            # --------------------------------
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
        # TODO: Добавить создание файла с кандидатами, если не удалось
        #  оставить 1
        if len(candidates) > 1:
            problem_items = [f'{item["name"]}: {item["id"]}' for item in
                             candidates]
            error_msg = (f'Для {content_title} проверьте имя '
                         f'файла/папки. Не удалось идентифицировать '
                         f'произведение. Кандидаты:\n '
                         f'{'\n'.join(problem_items)}')
            raise ALotOfContentError(error_msg)
        else:
            return candidates[0]
    raise ScraperError('Ошибка выполнения функции get_content')

def get_clean_info(
        raw_content: dict, content_type: str, season_numbers: list |  None):
    """
    Удаляет из ответа неиспользуемые данные.
    Для сезонов заменяет тип данных на словарь, где номер сезона ключ
    Args:
        raw_content: Исходная информация из API
        content_type: movie, episode или tv_show
        season_numbers: для tv_show список с номерами имеющихся локально сезонов
    Returns:
        content: Словарь с готовыми для сохранения данными.
    """
    validate_types_from_annotation()
    try:
        expected_content_types = ('tv_show', 'episode', 'movie')
        if content_type not in expected_content_types:
            raise ValueError(f'Неподдерживаемый тип контента. '
                             f'Ожидаются {", ".join(expected_content_types)}')
        if content_type == 'tv_show':
            key_map = TV_SHOW_INFO_STRUCTURE
        if content_type == 'episode':
            key_map = EPISODE_INFO_STRUCTURE
        if content_type == 'movie':
            key_map = FILM_INFO_STRUCTURE
        content = {}
        for tag, content_tag in key_map.items():
            if tag != 'seasons':
                content[tag] = raw_content.get(content_tag)
            else:
                seasons = {}
                for season in raw_content.get(tag):
                    season_num_api = int(season.get('season_number'))
                    if int(season_num_api) in season_numbers:
                        season['showtitle'] = content.get('title')
                        seasons[season_num_api] = season
                content[tag] = seasons
        return content

    except Exception as e:
        error_msg = (f'Ошибка при очистке ответа API для : {content_type} '
                     f'{type(e).__name__} - {str(e)}')
        raise NfoCreateError(error_msg) from e

def create_nfo(
        content: dict, path: str, content_type: str,
        file_name: str | None = None):
    """
    Создает nfo файл из исходного словаря.
    Args:
        content: Словарь с данными для сохранения в файле.
        path: папка для создания файла.
        content_type: movie или tv_show, episode.
        file_name: имя nfo файла, только для фильмов и эпизодов.

    Returns:

    """
    validate_types_from_annotation()
    expected_content_types = ('tv_show', 'episode', 'movie')
    if content_type not in expected_content_types:
        raise ValueError(f'Неподдерживаемый тип контента. '
                         f'Ожидаются {", ".join(expected_content_types)}')
    try:
        if content_type == 'tv_show':
            file_name = 'tvshow.nfo'
            root_name = 'tvshow'
        if content_type == 'episode':
            file_name = f'{file_name}.nfo'
            root_name = 'episodedetails'
        if content_type == 'movie':
            file_name = f'{file_name}.nfo'
            root_name = 'movie'

        nfo_path = os.path.join(path, file_name)
        root = etree.Element(root_name)
        for tag, content_key in content.items():
            # Обработка множественных тэгов
            if tag in ('genres', 'countries'):
                for elem in content_key:
                    elem_tag = etree.SubElement(root, tag)
                    elem_tag.text = str(elem.get('name'))

            # Обработка тэгов с вложенностью
            elif tag == 'actors':
                for actor in content_key:
                    tag_actor = etree.SubElement(root, 'actor')
                    for key, value in actor.items():
                        if key not in IMAGES_KEYS:
                            actor_elem = etree.SubElement(tag_actor, key)
                            actor_elem.text = str(value)
            # Обработка инфо о сезонах
            elif tag == 'seasons':
                for s_num, s_content in content_key.items():
                    season_plot = etree.SubElement(root, 'seasonplot')
                    season_plot.set('number', str(s_num))
                    season_plot.text = str(s_content.get('overview'))

            # Обработка остальных тэгов, пропускаем изображения
            else:
                if tag not in IMAGES_KEYS:
                    elem = etree.SubElement(root, tag)
                    elem.text = str(content_key)

        rough_xml = etree.tostring(root, encoding='utf-8',
                                   xml_declaration=True, pretty_print=True)
        final_xml = rough_xml.decode('utf-8')
        with open(nfo_path, 'w', encoding='utf-8') as f:
            f.write(final_xml)

    except Exception as e:
        error_msg = (f'Ошибка при создании nfo для: {content_type} в {path}:'
                     f'{type(e).__name__} - {str(e)}')
        raise NfoCreateError(error_msg) from e

def create_image(image_name: str, url_path: str, path:str):
    """
    Загружает и создает изображения.
    Args:
        image_name: Имя, с которым следует создать файл
        url_path: последний сегмент ссылки на изображения (/3851982849458.jpg)
        path: Адрес папки для сохранения

    Returns:

    """
    validate_types_from_annotation()
    os.makedirs(path, exist_ok=True)
    url = f'{TMDB_IMAGES}{url_path}'
    image = fetch_data('content', url=url)
    file_name = f'{image_name}.jpg'
    file_path = os.path.join(path, file_name)
    try:
        with open(file_path, 'wb') as f:
            f.write(image)
    except (PermissionError, OSError, IsADirectoryError) as e:
        raise CreateImageError(
            f'Ошибка при сохранении изображения {file_path}: {e}')

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
    else:
        url = TMDB_MOVIE_CREDITS.format(content_id)
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
        if len(cast) <= MAX_ACTORS:
            person_info = {}
            person_info['name'] = person.get('name')
            person_info['role'] = person.get('character')
            person_info['order'] = person.get('order')
            person_info['id'] = person.get('id')
            person_info['photo_url'] = person.get('profile_path')
            cast.append(person_info)
    for idx, person in enumerate(cast[:]):
        if not person.get('photo_url'):
            cast.pop(idx)

    return cast

def get_season_info(season_num, id):
    """
    Возвращает словарь с информацией о сезоне.
    Args:
        season_num: Номер сезона
        id: id сериала
    Returns:
        Словарь с общей информацией о сезоне и списком с информацией о сериях.
    """
    request_params = {'url': TMDB_GET_SEASON.format(id, season_num),
                      'headers': {'Authorization': f'Bearer {TMDB_TOKEN}'},
                      'params': {'language': 'ru-Ru'}
                      }

    # Проверка статуса ответа API
    season_data = fetch_data('json', **request_params)
    validate_types(request_data=(season_data, dict))
    episodes_data = season_data.get('episodes')
    if episodes_data and len(episodes_data) > 0:
        episodes_result = {}
        for episode in episodes_data:
            ep_number = episode['episode_number']
            episodes_result[ep_number] = episode
        return episodes_result
    raise NoContentError(f'TMDB_id - {id}:'
                         f'В ответе API нет информации о сезонах ')
