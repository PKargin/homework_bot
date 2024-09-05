import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiException

from exceptions import MissingTokensError, ResponseStatusError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('YANDEX_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT_ID')

ENV_VARS = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']

RETRY_PERIOD = 600

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)


def check_tokens():
    """Проверка доступности переменных окружения."""
    missing_vars = []
    for v in ENV_VARS:
        if globals().get(v) is None:
            missing_vars.append(v)
    if missing_vars:
        missing_vars_str = ", ".join(missing_vars)
        logger.critical(
            f'Отсутствуют переменные окружения: {missing_vars_str}!'
        )
    return missing_vars


def send_message(bot, message):
    """Отправка сообщения Телеботу."""
    logger.info('Начинаем отправку сообщения!')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение успешно отправлено: {message}.')
    except (ApiException, requests.RequestException) as e:
        logger.error(f'Ошибка при отправке сообщения: {e}.')


def get_api_answer(timestamp: int) -> dict:
    """Обращаемся к эндпоинту API."""
    params = {'from_date': timestamp}
    logger.info(
        f'Начало запроса к API с параметрами:{params, HEADERS, ENDPOINT}'
    )
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException as error:
        raise Exception(
            f'Во время подлючения к ендпоинту {ENDPOINT}'
            f'произошла ошибка: {error}'
            f'Параметры: {HEADERS, params}'
        )
    if response.status_code != HTTPStatus.OK:
        raise ResponseStatusError(
            'Ошибка в ответе сервера:'
            f'Парметры запроса: {params, HEADERS, ENDPOINT}'
            f'Код ответа сервера: {response.status_code}'
            f'Причина: {response.reason}'
            f'Контекст: {response.text}'
        )
    return response.json()


def check_response(response):
    """Проверка ответа API на соответствующие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API должен быть словарем, а получили {type(response)}!'
        )
    if 'homeworks' not in response:
        raise KeyError('Ключ "homeworks" отсутствует в ответе API.')
    if 'current_date' not in response:
        raise KeyError('Ключ "current_date" отсутствует в ответе API.')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            'Ключ "homeworks" должен содержать список, '
            f'а содержит {type(homeworks)}.'
        )
    return homeworks


def parse_status(homework):
    """Извлечение информации о домашке."""
    if 'status' not in homework:
        raise KeyError('Ключ "status" отстутствует в информации о домашке.')
    if 'homework_name' not in homework:
        raise KeyError(
            'Ключ "homework_name" отсутствует в информации о домашке.'
        )
    status = homework['status']
    homework_name = homework['homework_name']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Получен неизвестный статус "{status}"'
                         f'для домашки "{homework_name}".')
    verdict = HOMEWORK_VERDICTS.get(status)
    return f'Изменился статус проверки работы "{homework_name}": {verdict}'


def main():
    """Основная логика работы бота."""
    if missing_vars := check_tokens():
        raise MissingTokensError(
            'Отсутствуют необходимые переменные окружения: '
            f'{", ".join(missing_vars)}'
        )

    bot = TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if not homeworks:
                logger.debug("Список домашек пуст!")
            else:
                homework = homeworks[0]
                message = parse_status(homework)
                if send_message(bot, message):
                    timestamp = response.get('current_date', timestamp)
                    last_error = None
        except Exception as error:
            string = 'Сбой в работе программы:'
            logger.error(f'{string} {error}')
            if str(error) != last_error:
                send_message(bot, f'{string} {error}')
                last_error = str(error)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - '
               '%(message)s (%(filename)s:%(lineno)d, %(funcName)s)',
        handlers=logging.StreamHandler(sys.stdout)
    )
    logger.info("Дополнительная информация")
    logger.debug("Информация об отладке")
    logger.warning("Внимание")
    logger.error("Произошла ошибка")
    logger.critical("WAKE UP NEO, срочно звоним тимлиду!")
    main()
