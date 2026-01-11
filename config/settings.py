import os

from dotenv import load_dotenv

load_dotenv()

MEDIA_ROOT_PATH = os.getenv('media_root_path')
TELEGRAM_BOT_TOKEN = os.getenv('telegram_bot_token')
TELEGRAM_CHAT_ID = os.getenv('telegram_chat_id')
YEAR_STAMP = r'(19|20)\d{2}'
VIDEO_EXT = ('.mp4', '.mkv', '.avi', '.mov')

ENDPOINT_SEARCH_BY_KEYWORDS = 'https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword'
ENDPOINT_DATA_BY_FILM_ID = 'https://kinopoiskapiunofficial.tech/api/v2.2/films'
ENDPOINT_STAFF_BY_FILM_ID = 'https://kinopoiskapiunofficial.tech/api/v1/staff'
X_API_KEY = os.getenv('x_api_key')
MAX_ACTORS = 10
GET_ID_CACHE_SIZE = 100
GET_ID_TTL = 60*60*24
FILM_INFO_STRUCTURE = {
    'title': 'nameRu',
    'originaltitle': 'nameOriginal',
    'year': 'year',
    'plot': 'description',
    'runtime': 'filmLength',
    'rating': 'ratingKinopoisk',
    'votes': 'ratingKinopoiskVoteCount',
    'mpaa': 'ratingMpaa',
    'certification': 'ratingMpaa',
    'genres': 'genres',
    'countries': 'countries',
    'kinopoisk_id': 'kinopoiskId',
    'poster': 'posterUrl',
    'fanart': 'coverUrl'
}
# HEADERS = {'x-api-key': os.getenv('x_api_key')}
