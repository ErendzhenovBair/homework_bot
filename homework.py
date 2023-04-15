import logging
import os
import sys
import time

import requests
from requests.exceptions import RequestException
import telegram
from telegram import Bot

from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename='homework_result.log',
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    logger.debug('Проверка переменных окружения')
    tokens_exist = PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID
    if tokens_exist:
        logger.debug('Все переменные из окружения доступны')
        return True
    logger.critical('Переменные окружения не найдена')
    logger.debug('Программа принудительно остановлена')
    return False


def send_message(bot: Bot, message: str):
    """Отправляет сообщения в чат, определяемый переменной окружения."""
    try:
        logger.debug('Начало отправки')
        bot.send_message(
            TELEGRAM_CHAT_ID,
            message)
        logger.debug(f'Сообщение {message} отправлено')
    except Exception as error:
        logger.error('Не удалось отправить сообщение')
        raise error('Не удалось отправить сообщение')


def get_api_answer(timestamp: int) -> dict:
    """Делает запрос к эндпоинту API-сервиса."""
    logger.debug('Отправка запроса к эндпоинту')
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != 200:
            raise Exception(
                f'Ошибка запроса API: получен статус {response.status_code}')
        data = response.json()
        if 'error' in data and data['error'] == 'invalid_token':
            raise ValueError('Невалидный токен')
    except RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
        raise error(f'Ошибка при запросе к API: {error}')
    logger.debug(f'Ответ API получен {data}')
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
    if not check_tokens():
        logger.critical('Переменная окружения не найдена')
        sys.exit(1)
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
