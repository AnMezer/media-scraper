import os
import pprint
import re
import time
from http import HTTPStatus
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

_requests_per_day = 0
_requests_per_second = 0
_last_api_call_at: datetime

SPLITTERS = r'[_.()]'


logger_name = f'{__name__}'
logger = setup_logger(logger_name)
bot = TeleBot(token=TELEGRAM_BOT_TOKEN)

# Вспомогательные функции
# =========================


def check_vars():
    """Проверяет, наличие переменных для работы скрипта.

    Raises:
        MissingEnvironmentVariableError: Если хотя бы одна из переменных
            не определена или пустая.
    """
    variables = {
        '.env': {
            'MEDIA_ROOT_PATH': MEDIA_ROOT_PATH,
            'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
            'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
            'X_API_KEY': X_API_KEY
        },
        'settings.py': {
            'YEAR_STAMP': YEAR_STAMP,
            'VIDEO_EXT': VIDEO_EXT,
            'ENDPOINT_SEARCH_BY_KEYWORDS': ENDPOINT_SEARCH_BY_KEYWORDS,
            'ENDPOINT_DATA_BY_FILM_ID': ENDPOINT_DATA_BY_FILM_ID,
            'ENDPOINT_STAFF_BY_FILM_ID': ENDPOINT_STAFF_BY_FILM_ID
        }
    }
    missing_vars = []
    for file_name, vars_dict in variables.items():
        for var_name, var_value in vars_dict.items():
            if (var_value is None or
                    (isinstance(var_value, str) and var_value.strip() == '')):
                missing_vars.append(f'{file_name}: {var_name}')
    if missing_vars:
        error_message = (f'В переменных окружения не определены: '
                         f'{', '.join(missing_vars)}')
        logger.critical(error_message)
        raise MissingVariableError(error_message)


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
    logger.debug('Сообщение успешно отправлено в Telegram.')
    return True


def get_film_name_year(raw_file_name: str) -> tuple[str, str]:
    """Возвращает название и год выпуска из имени файла.

    Args:
        raw_file_name: Имя файла без расширения.

    Raises:
        ValueError: На вход получен тип данных не str.
        NoYearError: Год выпуска в имени файла не найден.

    Returns:
        Кортеж - (title, year)
    """
    validate_types(raw_file_name=(raw_file_name, str))

    match = re.search(YEAR_STAMP, raw_file_name)
    if match:
        year = match.group()
        raw_title = raw_file_name[:match.start()]
        title = re.sub(SPLITTERS, ' ', raw_title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title, year
    raise NoYearError(
        f'У файла {raw_file_name} год выпуска не найден.\n'
        f'Проверьте имя файла.')


def is_nfo_file_exists(video_file_name: str, files: list) -> bool:
    """Проверяет наличие *.nfo файла рядом с фильмом.

    Args:
        video_file_name: Имя файла фильма без расширения.
        files: Список файлов в папке с фильмом.

    Returns:
        True | False
    """
    validate_types(video_file_name=(video_file_name, str))

    nfo_file_name = video_file_name + '.nfo'
    for file_name in files:
        if file_name == nfo_file_name:
            return True
    return False


@ttl_cache(maxsize=GET_ID_CACHE_SIZE, ttl=GET_ID_TTL)
def get_film_id(title: str, year: str) -> tuple[bool, str, str] | None:
    """Отправляет запрос к kinopoiskapiunofficial API для поиска
      kinopoisk_id фильма.
    Ищет в ответе совпадение по году выпуска,
    если год в исходных данных отсутствовал или совпадений не найдено,
    то возвращает kinopoisk_id фильма с самым свежим годом релиза.
    Args:
        title: Название фильма.
        year: Год выпуска.

    Raises:
        TpeError: Если переданы аргументы неверного типа.
        APIConnectionError: Если не получен или статус отличен от 200.
        TypeError: Если тип данных ответа отличается от ожидаемого.
        APIAnswerWrongDataError: Искомый ключ в ответе отсутствует.
        NoFilmsError: В ответе нет ни одного фильма.
        APIAnswerWrongDataError: Формат года в ответе не соответствует ожидаемому.

    Returns:
        is_year_found - найдено ли при поиске совпадение по году выпуска.
        kinopoisk_id - id для поиска информации по фильму.
        msg - сообщение с результатом работы, для дальнейшего логгирования.
    """
    last_release_year = '0000'
    last_released_film_idx = 0
    is_year_found = False
    request_params = {'url': ENDPOINT_SEARCH_BY_KEYWORDS,
                      'headers': {'x-api-key': X_API_KEY},
                      'params': {'keyword': title}}

    validate_types(year=(year, str), title=(title, str))

    try:
        request_films = requests.get(**request_params)
    except RequestException as e:
        message = (f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(message)
    status_code = request_films.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None

    request_data = request_films.json()
    validate_types(request_data=(request_data, dict))
    if 'films' not in request_data:
        msg = 'Ключ films отсутствует в ответе API'
        raise APIAnswerWrongDataError(msg)

    films = request_data['films']
    if len(films) == 0:
        msg = (f'Поиск ({title}). В ответе API список films пуст.\n'
               f'Проверьте имя файла.')
        raise NoFilmsError(msg)

    for idx, film in enumerate(films):
        film_year: str = film['year']
        if len(film_year) != 4 or not film_year.isdigit():
            msg = 'В ответе формат данных года не соответствует ожидаемым'
            raise APIAnswerWrongDataError(msg)
        if film_year > last_release_year:
            last_release_year = film_year
            last_released_film_idx = idx
        if not is_year_found:
            if film_year == year:
                is_year_found = True
                msg = (f'Данные о фильме {film['nameRu']} ({year}) '
                       f'успешно получены')
                return is_year_found, str(films[idx]['filmId']), msg

        msg = (f'Год выпуска при поиске {title} ({year}) '
               f'не найден в ответе API, сохранены данные о фильме '
               f'с самым свежим годом релиза.')
    return is_year_found, str(films[last_released_film_idx]['filmId']), msg


@ttl_cache(maxsize=GET_ID_CACHE_SIZE, ttl=GET_ID_TTL)
def get_raw_film_info(film_id: str) -> dict | None:
    """Отправляет запрос к kinopoiskapiunofficial API для поиска
      информации о фильме по kinopoisk_id.

    Args:
        film_id: kinopoisk_id

    Raises:
        TypeError: Если переданы аргументы неверного типа.
        APIConnectionError: Если не получен или статус отличен от 200.
        TypeError: Если тип данных ответа отличается от ожидаемого.

    Returns:
        raw_film_info - сырая информация о фильме.
    """
    validate_types(film_id=(film_id, str))

    url = f'{ENDPOINT_DATA_BY_FILM_ID}/{film_id}'
    request_params = {'url': url,
                      'headers': {'x-api-key': X_API_KEY}}

    try:
        request_film_info = requests.get(**request_params)
    except RequestException as e:
        message = (f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(message)
    status_code = request_film_info.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None
    raw_film_info = request_film_info.json()

    validate_types(raw_film_info=(raw_film_info, dict))
    return raw_film_info


@ttl_cache(maxsize=GET_ID_CACHE_SIZE, ttl=GET_ID_TTL)
def get_raw_staff_info(
        film_id: str, max_actors: int = MAX_ACTORS) -> dict | None:
    """Отправляет запрос к kinopoiskapiunofficial API для поиска
      информации об актерах и режиссерах по kinopoisk_id.

    Args:
        film_id: kinopoisk_id

    Raises:
        TypeError: Если переданы аргументы неверного типа.
        APIConnectionError: Если не получен или статус отличен от 200.
        TypeError: Если тип данных ответа отличается от ожидаемого.

    Returns:
        _description_
    """
    validate_types(film_id=(film_id, str))

    raw_filtered_staff: dict = {'ACTORS': [],
                                'DIRECTORS': []}
    url = f'{ENDPOINT_STAFF_BY_FILM_ID}?filmId={film_id}'
    request_params = {'url': url,
                      'headers': {'x-api-key': X_API_KEY}}
    try:
        request_staff_info = requests.get(**request_params)
    except RequestException as e:
        message = (f'Ошибка при получении ответа от API {request_params}: {e}')
        raise APIConnectionError(message)
    status_code = request_staff_info.status_code
    check_request_status(status_code)
    if status_code == HTTPStatus.NOT_FOUND:
        return None

    raw_film_staff_info = request_staff_info.json()

    validate_types(raw_film_staff_info=(raw_film_staff_info, list))

    for person in raw_film_staff_info:
        if (person['professionKey'] == 'ACTOR'
                and len(raw_filtered_staff['ACTORS']) < max_actors):
            raw_filtered_staff['ACTORS'].append(person)
        if person['professionKey'] == 'DIRECTOR':
            raw_filtered_staff['DIRECTORS'].append(person)
    return raw_filtered_staff


def get_clean_film_info(raw_film_info: dict) -> tuple[dict, dict, str]:
    """Подготавливает словарь для последующего сохранения данных в *.nfo файл.

    Args:
        raw_film_info: Сырая информация о фильме, полученная от API.

    Raises:
        TypeError: Если аргументом получен не ожидаемый тип данных.

    Returns:
        clean_film_info - Готовый для сохранения словарь.
        posters_urls - Ссылка для загрузки обложки фильма.
        empty_fields_str - Строка с перечислением полей,
                           которые отсутствовали в исходных данных.
    """
    validate_types(raw_film_info=(raw_film_info, dict))

    empty_fields = []
    clean_film_info = {}
    posters_urls = {'poster': None,
                    'cover': None}       
    for key, api_field in FILM_INFO_STRUCTURE.items():
        value = raw_film_info.get(api_field)
        if value:
            if key == 'runtime':
                try:
                    clean_film_info[key] = int(value) * 60
                except (TypeError, ValueError):
                    clean_film_info[key] = None
                    empty_fields.append(key)
            elif key in ('poster', 'fanart'):
                posters_urls[key] = value
            else:
                clean_film_info[key] = value
        else:
            empty_fields.append(key)
    empty_fields_str = ', '.join(empty_fields)
    return clean_film_info, posters_urls, empty_fields_str


def get_clean_staff_info(raw_staff_info: dict) -> tuple[dict, dict, str]:
    """Подготавливает словари для последующего сохранения данных в *.nfo файл
    и загрузки фото актеров.

    Args:
        raw_staff_info: Сырая информация о фильме, полученная от API.

    Raises:
        TypeError: Если аргументом получен не ожидаемый тип данных.

    Returns:
        clean_staff_info - Готовый для сохранения словарь с участниками.
        staff_posters - Словарь со ссылками на фото участников.
        empty_posters - Участники у которых ссылка на фото отсутствовала.
    """
    if raw_staff_info is None or not isinstance(raw_staff_info, dict):
        msg = f'Для film_id ожидался dict, получен {type(raw_staff_info)}'
        raise TypeError(msg)

    person: dict
    person_name = None
    clean_staff_info: dict = {'ACTORS': [],
                              'DIRECTORS': []}
    staff_posters = {}
    empty_posters = []
    for profession, persons in raw_staff_info.items():
        for person in persons:
            person_name = None
            if person.get('nameRu'):
                person_name = person['nameRu']
            elif person.get('nameEn'):
                person_name = person['nameEn']
            if person_name:
                clean_staff_info[profession].append(
                    {'name': person_name,
                     'role': person['description']}
                )
            poster_url = person.get('posterUrl')
            if poster_url:
                staff_posters[person_name] = person['posterUrl']
            else:
                empty_posters.append(person_name)
    empty_posters_str = ', '.join(empty_posters)
    return clean_staff_info, staff_posters, empty_posters_str


def create_nfo(clean_film_info: dict, clean_staff_info: dict,
               path: str, raw_file_name: str) -> tuple[bool, str]:
    """Создает *.nfo файл рядом с фильмом.

    Args:
        clean_film_info: Словарь с информацией о фильме.
        clean_staff_info: Словарь с информацией об участниках
        path: Путь к фильму.
        raw_file_name: Имя файла для *.nfo

    Raises:
        TypeError: Если тип аргументов не соответствует ожидаемым.
    """
    try:
        validate_types(clean_film_info=(clean_film_info, dict),
                       clean_staff_info=(clean_staff_info, dict),
                       path=(path, str),
                       raw_file_name=(raw_file_name, str))

        nfo_path = os.path.join(path, raw_file_name + '.nfo')
        root = Element('movie')
        for tag, tag_value in clean_film_info.items():
            if tag_value:
                if tag == 'genres':
                    for genre in tag_value:
                        SubElement(root, 'genre').text = str(genre['genre'])
                elif tag == 'countries':
                    for country in tag_value:
                        SubElement(root, 'country').text = str(
                            country['country'])
                else:
                    SubElement(root, tag).text = str(tag_value)
        for profession, persons in clean_staff_info.items():
            if profession == 'ACTORS':
                for idx, person in enumerate(persons):
                    actor_root = SubElement(root, 'actor')
                    SubElement(actor_root, 'name').text = person.get('name')
                    SubElement(actor_root, 'role').text = person.get('role')
                    SubElement(actor_root, 'order').text = str(idx)
            elif profession == 'DIRECTORS':
                for idx, person in enumerate(persons):
                    SubElement(root, 'director').text = person.get('name')
        # ------------------
        rough_xml = tostring(root, encoding='unicode', xml_declaration=True)
        reparsed_xml = minidom.parseString(rough_xml)
        pretty_xml = reparsed_xml.toprettyxml(indent='  ', encoding='utf-8')
        # Убираем лишние пустые строки от toprettyxml
        lines = [line for line in pretty_xml.decode('utf-8').splitlines() if line.strip()]
        final_xml = '\n'.join(lines)
        # -------------------
        with open(nfo_path, 'w', encoding='utf-8') as f:
            f.write(final_xml)
        return True, '*.nfo файл успешно создан.'
    except Exception as e:
        error_msg = f'Ошибка при создании *.nfo: {e}'
        return False, str(error_msg)


def create_posters(posters_urls: dict, staff_posters: dict,
                   root: str, raw_file_name: str) -> tuple[bool, str]:
    """Сохраняет постеры и фото актеров.

    Args:
        posters_urls: Ссылки на постеры.
        staff_posters: Ссылки на фото актеров.
        root: Путь к папке сохранения.
        raw_file_name: Исходное имя файла без расширения.
    """
    try:
        validate_types(posters_urls=(posters_urls, dict),
                       staff_posters=(staff_posters, dict),
                       root=(root, str),
                       raw_file_name=(raw_file_name, str))

        for key, value in posters_urls.items():
            if value:
                file_root = os.path.join(root, f'{raw_file_name}-{key}.jpg')
                picture = requests.get(url=posters_urls[key])
                with open(file_root, 'wb') as f:
                    f.write(picture.content)

        for name, poster_url in staff_posters.items():
            name = re.sub(' ', '_', name)
            actors_dir = os.path.join(root, '.actors')
            os.makedirs(actors_dir, exist_ok=True)
            poster_root = os.path.join(actors_dir, f"{name}.jpg")
            poster = requests.get(url=poster_url)
            with open(poster_root, 'wb') as f:
                f.write(poster.content)
        return True, 'Постеры успешно сохранены.'
    except Exception as e:
        error_msg = f'Ошибка при сохранении постеров: {e}'
        return False, str(error_msg)


def process_folder(root: str, files: list):
    files_processed = 0
    message = ''
    for file in files:
        raw_file_name, ext = os.path.splitext(file)
        if ext in VIDEO_EXT:
            if not is_nfo_file_exists(raw_file_name, files):
                files_processed += 1
                title, year = get_film_name_year(raw_file_name)
                result_film_id = get_film_id(title, year)
                if result_film_id is None:
                    raise NotFoundError(f'В API для {title} ({year}) '
                                        f'id не найден')
                is_ok_film_id, film_id, msg_id = result_film_id
                result_raw_film_info = get_raw_film_info(film_id)
                if result_raw_film_info is None:
                    raise NotFoundError(f'В API для id {film_id}) '
                                        f'Информация о фильме не найдена')
                raw_film_info = result_raw_film_info
                result_raw_staff_info = get_raw_staff_info(film_id, MAX_ACTORS)
                if result_raw_staff_info is None:
                    raise NotFoundError(f'В API для id {film_id}) '
                                        f'Информация об актерах не найдена')
                (clean_film_info, posters_urls,
                 empty_fields) = get_clean_film_info(raw_film_info)
                message += (f'{clean_film_info['title']} '
                            f'({clean_film_info['year']}):')

                (clean_staff_info, staff_posters,
                 empty_posters) = get_clean_staff_info(result_raw_staff_info)

                is_ok, msg = create_nfo(
                    clean_film_info, clean_staff_info, root, raw_file_name)
                if is_ok:
                    logger.info(f'{title} ({year}): {msg}')
                else:
                    logger.warning(f'{title} ({year}): {msg}')
                message += f'\n- {msg}'

                is_ok, msg = create_posters(
                    posters_urls, staff_posters, root, raw_file_name)
                if is_ok:
                    logger.info(f'{title} ({year}): {msg}')
                else:
                    logger.warning(f'{title} ({year}): {msg}')
                message += f'\n- {msg}'

                if not is_ok_film_id:
                    logger.warning(msg_id) 
                    message += f'\n- {msg_id}'
    return files_processed, message


# =========================


def main():
    latest_error_msg = ''
    new_files = 0
    while True:
        new_files = 0
        bot_message = ''

        try:
            check_vars()
            for root, dirs, files in os.walk(MEDIA_ROOT_PATH):
                if TV_SHOWS_FOLDER in dirs:
                    dirs.remove(TV_SHOWS_FOLDER)
                files_processed, message = process_folder(root, files)
                if message:
                    bot_message += f'**** {message}\n\n'
                new_files += files_processed
            if new_files > 0:
                bot_message += f'*!* Новых фильмов в медиатеке - {new_files}.'
                send_message(bot, bot_message)
            else:
                print('Новых файлов нет')
        except Exception as error:
            error_message = f'Сбой в работе программы:\n{error}'
            if error_message != latest_error_msg:
                try:
                    send_message(bot, error_message)
                    latest_error_msg = error_message
                except Exception:
                    logger.error('Ошибка при отправке сообщения')
        time.sleep(10)


if __name__ == '__main__':
    main()
