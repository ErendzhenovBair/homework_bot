import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
from requests.exceptions import RequestException
import telegram
from telegram import Bot

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

# Сообщения для функции check_tokens
START_MESSAGE_CHECK_TOKENS = 'Проверка переменных окружения'
END_MESSAGE_CHECK_TOKENS = 'Все переменные из окружения доступны'
ERROR_MESSAGE_TOKENS = 'Переменная окружения {token} не найдена'

# Сообщения для функции send_message
MESSAGE_SEND_START = 'Начало отправки'
MESSAGE_SEND_SUCCESSFULLY = 'Сообщение: {message} отправлено'
MESSAGE_SEND_ERROR = 'Не удалось отправить сообщение: {message}. {error}'

# Сообщения для функции get_api_answer
API_ANSWER_LOG = (
    'Начало запроса к {url}, {headers}, c значениями {params}')
ERROR_ANSWER = (
    'Ошибка подключения {url}, {headers}, c значениями {params}, '
    'ошибка: {error}')
REQUEST_FAILED_MESSAGE = (
    'Получен неожиданный статус API - {status}, {url}, '
    '{headers}, c значениями {params}')
SERVER_FAILURE_MESSAGE = (
    'Ошибка сервера: {error} - {value}. {url}, {headers}, {params}')

# Сообщения для функции check_response
CHECK_RESPONSE_START_MESSAGE = 'Проверка соответствия данных'
NOT_DICT_MESSAGE = (
    'Ожидаемый тип данных - словарь, но получен (тип {type_name})')
KEY_ERROR_MESSAGE = 'Ключ homeworks не найден'
NOT_LIST_MESSAGE = (
    'Ожидаемый тип данных - список, но получен (тип {type_name})')

# Сообщения для функции parse_status
PARSE_STATUS_START_MESSAGE = 'Извлечение статуса домашней работы'
EMPTY_HOMEWORK_DICT_MESSAGE = 'Словарь homework пуст'
MISSING_HOMEWORK_NAME_MESSAGE = 'Отсутствует ключhomework_name'
MISSING_DOCUMENTED_STATUS_MESSAGE = 'Отсутствует документированный статус'
UNEXPECTED_STATUS_MESSAGE = 'Неожиданный статус проверки {status}'
REVIEW_STATUS = (
    'Изменился статус проверки работы "{0}". {1}')

# Сообщения для функции main
BOT_START_MESSAGE = 'Проверка запущена {__name__}'
PROGRAMM_FAILURE_ERROR_MESSAGE = 'Сбой в работе программы: {error}'

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILENAME = os.path.join(BASE_DIR, 'homework_result.log')
FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.DEBUG,
    format=FORMAT,
    handlers=[
        logging.FileHandler(FILENAME, encoding='UTF-8', mode='w')]
)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    logger.debug(START_MESSAGE_CHECK_TOKENS)
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    for token in tokens:
        if not token:
            logger.critical(ERROR_MESSAGE_TOKENS.format(token=token))
            raise ValueError(f'Переменная окружения {token} не найдена')
    logger.debug(END_MESSAGE_CHECK_TOKENS)
    return True


def send_message(bot: Bot, message: str):
    """Отправляет сообщения в чат, определяемый переменной окружения."""
    try:
        logger.debug(MESSAGE_SEND_START)
        bot.send_message(
            TELEGRAM_CHAT_ID,
            message)
        logger.debug(MESSAGE_SEND_SUCCESSFULLY)
    except Exception as error:
        logger.error(MESSAGE_SEND_SUCCESSFULLY.format(
            message=message, error=error), exc_info=True)
        raise ValueError(MESSAGE_SEND_SUCCESSFULLY.format(
            message=message, error=error))


def get_api_answer(timestamp: int) -> dict:
    """Делает запрос к эндпоинту API-сервиса."""
    params = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': timestamp}
    )
    logger.debug(API_ANSWER_LOG.format(**params))
    try:
        response = requests.get(**params)
    except RequestException as error:
        raise ConnectionError(
            ERROR_ANSWER.format(error=error, **params))
    if response.status_code != 200:
        raise RuntimeError(
            REQUEST_FAILED_MESSAGE.format(
                status=response.status_code, **params))
    data = response.json()
    for error in ('code', 'error'):
        if error in data:
            raise RuntimeError(
                SERVER_FAILURE_MESSAGE.format(
                    error=error, value=data[error], **params))
    return data


def check_response(response: dict) -> list:
    """Проверяет ответ API на соответствие документации."""
    logger.debug(CHECK_RESPONSE_START_MESSAGE)
    if not isinstance(response, dict):
        raise TypeError(NOT_DICT_MESSAGE.format(
            type_name=type(response)))
    if 'homeworks' not in response:
        raise KeyError(KEY_ERROR_MESSAGE)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(NOT_LIST_MESSAGE.format(
            type_name=type(homeworks)))
    return homeworks


def parse_status(homework: dict) -> str:
    """Извлекает из информации о домашней работе статус этой работы."""
    logger.debug(PARSE_STATUS_START_MESSAGE)
    if not homework:
        raise KeyError(EMPTY_HOMEWORK_DICT_MESSAGE)
    if 'homework_name' not in homework:
        raise KeyError(MISSING_HOMEWORK_NAME_MESSAGE)
    if 'status' not in homework:
        raise KeyError(MISSING_DOCUMENTED_STATUS_MESSAGE)
    status = homework.get('status')
    homework_name = homework.get('homework_name')
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            UNEXPECTED_STATUS_MESSAGE.format(
                status=status))
    return (REVIEW_STATUS.format(homework_name, HOMEWORK_VERDICTS[status]))


def main():
    """Основная логика работы бота."""
    logger.info(BOT_START_MESSAGE)
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    previous_error = None
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks and send_message(bot, parse_status(homeworks[0])):
                timestamp = response.get(
                    'current_date', timestamp)
        except Exception as error:
            message = PROGRAMM_FAILURE_ERROR_MESSAGE.format(
                error=error)
            logger.error(message)
            if message != previous_error and send_message(bot, message):
                previous_error = error
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
