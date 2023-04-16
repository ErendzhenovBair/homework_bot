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

FILENAME = os.path.join(os.path.expanduser('~'), __file__ + '.log')
FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
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
FAILED_REQUEST = ('Получен неожиданный статус API - {status}, {url}, '
                  '{headers}, c значениями {params}')
SERVER_FAILURES = (
    'Ошибка сервера: {error} - {value}. {url}, {headers}, {params}')


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    format=FORMAT,
    handlers=[
        logging.FileHandler(FILENAME, encoding='UTF-8', mode='w'),
        logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


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
            FAILED_REQUEST.format(
                status=response.status_code, **params))
    data = response.json()
    for error in ('code', 'error'):
        if error in data:
            raise RuntimeError(SERVER_FAILURES.format(
                error=error, value=data[error], **params))
    return data


def check_response(response: dict) -> list:
    """Проверяет ответ API на соответствие документации."""
    logger.debug('Проверка соответствия данных')
    if not isinstance(response, dict):
        logger.error('Тип данных отличается от ожидаемого')
        raise TypeError(
            f'Ожидаемый тип данных - словарь, получен {type(response)}')
    if 'homeworks' not in response:
        logger.error('Отсутствует ключ homeworks')
        raise KeyError('Ключ homeworks не найден')
    if 'current_date' not in response:
        logger.error('Отсутствует ключ current_date')
        raise KeyError('Ключ homeworks не найден')
    if not isinstance(response['homeworks'], list):
        logger.error('Тип данных отличается от ожидаемого')
        raise TypeError('Ожидаемый тип данных - список')
    return response['homeworks']


def parse_status(homework: dict) -> str:
    """Извлекает из информации о домашней работе статус этой работы."""
    logger.debug('Извлечение статуса домашней работы')
    if not homework:
        logger.error('Словарь homework пуст')
        raise KeyError('Словарь homework пуст')
    if 'homework_name' not in homework:
        logger.error('Отсутствует ключ homework_name')
        raise KeyError('Отсутствует ключhomework_name')
    if 'status' not in homework:
        logger.error('Отсутствует документированный статус')
        raise KeyError('Отсутствует документированный статус')
    status = homework.get('status')
    homework_name = homework.get('homework_name')
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f'{status} отсутствует в словаре homework_verdicts')
    verdict = HOMEWORK_VERDICTS[status]
    logger.debug('Статус извлечен')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    logger.info(f'Проверка запущена {__name__}')
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    previous_homework = None
    previous_error = None
    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework and homework != previous_homework:
                message = parse_status(homework[0])
                send_message(bot, message)
                previous_homework = homework
                timestamp = response['current_date']
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if error != previous_error:
                send_message(bot, message)
                previous_error = error
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
