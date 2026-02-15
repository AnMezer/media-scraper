import os

from dotenv import load_dotenv

load_dotenv()

MEDIA_ROOT_PATH = os.getenv('media_root_path')
MOVIES_FOLDER = 'Movies'
CARTOONS_FOLDER = 'Cartoons'
TV_SHOWS_FOLDER = 'Serials'
TELEGRAM_BOT_TOKEN = os.getenv('telegram_bot_token')
TELEGRAM_CHAT_ID = os.getenv('telegram_chat_id')
YEAR_STAMP = r'(19|20)\d{2}'
VIDEO_EXT = ('.mp4', '.mkv', '.avi', '.mov')

ENDPOINT_SEARCH_BY_KEYWORDS = 'https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword'
ENDPOINT_DATA_BY_FILM_ID = 'https://kinopoiskapiunofficial.tech/api/v2.2/films'
ENDPOINT_STAFF_BY_FILM_ID = 'https://kinopoiskapiunofficial.tech/api/v1/staff'
TMDB_SEARCH_SHOW = 'https://api.themoviedb.org/3/search/tv'
TMDB_GET_SHOW = 'https://api.themoviedb.org/3/tv'
TMDB_IMAGES = 'https://image.tmdb.org/t/p/w1280'
TMDB_SHOW_CREDITS = 'https://api.themoviedb.org/3/tv/{}/credits'
X_API_KEY = os.getenv('x_api_key')
TMDB_TOKEN = os.getenv('tmdb_api_token')
MAX_ACTORS = 10
GET_ID_CACHE_SIZE = 100
GET_ID_TTL = 60*60*24
DAY_LIMIT = 500
SECOND_LIMIT = 4
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
TV_SHOW_INFO_STRUCTURE = {
    'title': 'name',
    'originaltitle': 'original_name',
    'premiered': 'first_air_date',
    'plot': 'overview',
    'rating': 'vote_average',
    'votes': 'vote_count',
    'status': 'status',
    'genres': 'genres',
    'countries': 'production_countries',
    'TMDB_id': 'id',
    'tagline': 'tagline',
    'poster': 'poster_path',
    'fanart': 'backdrop_path',
    'seasons': 'seasons'


}
SERIES_INFO_STRUCTURE = {
    'title': 'name',
    'showtitle': '',
    'season': '',
    'episode': '',
    'plot': 'overview',
    'aired': '',
    'TMDB_id': 'id',

}
# HEADERS = {'x-api-key': os.getenv('x_api_key')}
