import inspect
import logging
import platform
import re
import time
from http import HTTPStatus

import pytest
import requests
import telebot

import tests.check_utils as check_utils

old_sleep = time.sleep


def create_mock_response_get_with_custom_status_and_data(
        random_timestamp, http_status, data
):
    def mocked_response(*args, **kwargs):
        return check_utils.MockResponseGET(
            *args, random_timestamp=random_timestamp,
            http_status=http_status, data=data, **kwargs
        )

    return mocked_response


def get_mock_telegram_bot(monkeypatch, random_message):
    def mock_telegram_bot(random_message=random_message, *args, **kwargs):
        return check_utils.MockTelegramBot(
            *args, message=random_message, **kwargs
        )

    monkeypatch.setattr(telebot, 'TeleBot', mock_telegram_bot)
    return telebot.TeleBot(token='')


class TestHomework:
    HOMEWORK_VERDICTS = {
        'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
        'reviewing': 'Работа взята на проверку ревьюером.',
        'rejected': 'Работа проверена: у ревьюера есть замечания.'
    }
    ENV_VARS = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
    HOMEWORK_CONSTANTS = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN',
                          'TELEGRAM_CHAT_ID', 'RETRY_PERIOD',
                          'ENDPOINT', 'HEADERS', 'HOMEWORK_VERDICTS')
    HOMEWORK_FUNC_WITH_PARAMS_QTY = {
        'send_message': 2,
        'get_api_answer': 1,
        'check_response': 1,
        'parse_status': 1,
        'check_tokens': 0,
        'main': 0
    }
    RETRY_PERIOD = 600
    INVALID_RESPONSES = {
        'no_homework_key': check_utils.InvalidResponse(
            {
                "current_date": 123246
            },
            'homeworks'
        ),
        'not_dict_response': check_utils.InvalidResponse(
            [{
                'homeworks': [
                    {
                        'homework_name': 'hw123',
                        'status': 'approved'
                    }
                ],
                "current_date": 123246
            }],
            None
        ),
        'homeworks_not_in_list': check_utils.InvalidResponse(
            {
                'homeworks':
                    {
                        'homework_name': 'hw123',
                        'status': 'approved'
                    },
                'current_date': 123246
            },
            None
        )
    }
    NOT_OK_RESPONSES = {
        500: (
            create_mock_response_get_with_custom_status_and_data(
                random_timestamp=1000198000,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                data={}
            )
        ),
        401: (
            create_mock_response_get_with_custom_status_and_data(
                random_timestamp=1000198991,
                http_status=HTTPStatus.UNAUTHORIZED,
                data={
                    'code': 'not_authenticated',
                    'message': 'Учетные данные не были предоставлены.',
                    'source': '__response__'
                }
            )
        ),
        204: (
            create_mock_response_get_with_custom_status_and_data(
                random_timestamp=1000198992,
                http_status=HTTPStatus.NO_CONTENT,
                data={}
            )
        )
    }

    @pytest.mark.timeout(1, method='thread')
    def test_homework_const(self, homework_module):
        for const in self.HOMEWORK_CONSTANTS:
            check_utils.check_default_var_exists(homework_module, const)
        assert getattr(homework_module, 'RETRY_PERIOD') == self.RETRY_PERIOD, (
            'Не изменяйте переменную `RETRY_PERIOD`, её значение должно '
            f'быть равно `{self.RETRY_PERIOD}`.'
        )
        student_verdicts = getattr(homework_module, 'HOMEWORK_VERDICTS')
        assert student_verdicts == self.HOMEWORK_VERDICTS, (
            'Не изменяйте значение переменной `HOMEWORK_VERDICTS`.'
        )

    def test_bot_init_not_global(self, homework_module):
        for var in homework_module.__dict__:
            assert not isinstance(
                getattr(homework_module, var),
                telebot.TeleBot
            ), (
                'Убедитесь, что бот инициализируется только в функции '
                '`main()`.'
            )

    def test_logger(self, homework_module):
        assert hasattr(homework_module, 'logging'), (
            'Убедитесь, что логирование бота настроено.'
        )
        logging_config_pattern = re.compile(
            r'(logging\.basicConfig ?\()'
        )
        hw_source = check_utils.get_clean_source_code(
            inspect.getsource(homework_module)
        )
        logging_config = re.search(logging_config_pattern, hw_source)
        get_logger_pattern = re.compile(r'getLogger ?\(')
        logger = re.search(get_logger_pattern, hw_source)
        assert any((logging_config, logger)), (
            'Убедитесь, что логирование бота настроено с помощью '
            'функции `logging.basicConfig()` или класса `Logger` '
            '(`logging.getLogger()`).'
        )

    def test_request_call(
            self, monkeypatch, current_timestamp, homework_module
    ):
        func_name = 'get_api_answer'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        def check_request_call(
                url, current_timestamp=current_timestamp, **kwargs
        ):
            expected_url = (
                'https://practicum.yandex.ru/api/user_api/homework_statuses'
            )
            assert url.startswith(expected_url), (
                'Проверьте адрес, на который отправляются запросы.'
            )
            assert 'headers' in kwargs, (
                'Проверьте, что в запрос к API передан заголовок.'
            )
            assert 'Authorization' in kwargs['headers'], (
                'Проверьте, что в заголовках запроса передано поле '
                '`Authorization`.'
            )
            assert kwargs['headers']['Authorization'].startswith('OAuth '), (
                'Проверьте, что заголовок `Authorization` '
                'начинается с `OAuth`.'
            )
            assert 'params' in kwargs, (
                'Проверьте, что в запросе переданы параметры `params`.'
            )
            assert 'from_date' in kwargs['params'], (
                'Проверьте, что в параметрах к запросу передан параметр '
                '`from_date`.'
            )
            try:
                from_date = int(kwargs['params']['from_date'])
                assert from_date == int(current_timestamp), (
                    'Проверьте, что в параметре `from_date` передан timestamp.'
                )
            except ValueError:
                raise AssertionError(
                    'Проверьте, что в параметре `from_date` передано число.'
                )

        monkeypatch.setattr(requests, 'get', check_request_call)
        try:
            homework_module.get_api_answer(current_timestamp)
        except AssertionError:
            raise
        except Exception:
            pass

    def test_get_api_answers(
            self, monkeypatch, random_timestamp, current_timestamp,
            homework_module
    ):
        func_name = 'get_api_answer'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        def mock_response_get(*args, **kwargs):
            return check_utils.MockResponseGET(
                *args, random_timestamp=random_timestamp,
                current_timestamp=current_timestamp, **kwargs
            )

        monkeypatch.setattr(requests, 'get', mock_response_get)

        result = homework_module.get_api_answer(current_timestamp)
        assert isinstance(result, dict), (
            f'Проверьте, что функция `{func_name}` возвращает словарь.'
        )

    @pytest.mark.parametrize('response', NOT_OK_RESPONSES.values())
    def test_get_not_200_status_response(
            self, monkeypatch, current_timestamp, response, homework_module
    ):
        func_name = 'get_api_answer'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        monkeypatch.setattr(requests, 'get', response)
        try:
            homework_module.get_api_answer(current_timestamp)
        except Exception:
            pass
        else:
            raise AssertionError(
                f'Убедитесь, что в функции `{func_name}` обрабатывается '
                'ситуация, когда API домашки возвращает код, отличный от 200.'
            )

    def test_get_api_answer_with_request_exception(
            self, current_timestamp, monkeypatch, homework_module
    ):
        func_name = 'get_api_answer'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        def mock_request_get_with_exception(*args, **kwargs):
            raise requests.RequestException('Something wrong')

        monkeypatch.setattr(requests, 'get', mock_request_get_with_exception)
        try:
            homework_module.get_api_answer(current_timestamp)
        except requests.RequestException as e:
            raise AssertionError(
                f'Убедитесь, что в функции `{func_name}` обрабатывается '
                'ситуация, когда при запросе к API возникает исключение '
                '`requests.RequestException`.'
            ) from e
        except Exception:
            pass

    def test_parse_status_with_expected_statuses(self, homework_module):
        func_name = 'parse_status'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        test_data = {
            "id": 123,
            "homework_name": "Homework test",
            "reviewer_comment": "Всё нравится",
            "date_updated": "2020-02-13T14:40:57Z",
            "lesson_name": "Итоговый проект"
        }
        for status_key in self.HOMEWORK_VERDICTS.keys():
            test_data['status'] = status_key

            result = homework_module.parse_status(test_data)
            assert isinstance(result, str), (
                f'Проверьте, что функция `{func_name}` возвращает строку.'
            )
            assert result.startswith(
                'Изменился статус проверки работы '
                f'"{test_data["homework_name"]}"'
            ), (
                f'Проверьте, что в ответе функции `{func_name}` содержится '
                'название домашней работы.'
            )
            assert result.endswith(
                self.HOMEWORK_VERDICTS[status_key]
            ), (
                f'Проверьте, что функция `{func_name}` возвращает '
                f'правильное сообщение для статуса `{status_key}`.'
            )

    def test_parse_status_with_unknown_status(self, homework_module):
        func_name = 'parse_status'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        unknown_status = 'unknown'
        homework_with_invalid_status = [
            {
                'homework_name': 'hw123',
                'status': unknown_status
            },
            {
                'homework_name': 'hw123'
            }
        ]
        for hw in homework_with_invalid_status:
            try:
                homework_module.parse_status(hw)
            except KeyError as e:
                if repr(e) == f"KeyError('{unknown_status}')":
                    raise AssertionError(
                        f'Убедитесь, что функция `{func_name}` обрабатывает '
                        'случай, когда API домашки возвращает '
                        'недокументированный статус домашней работы либо '
                        'домашку без статуса.'
                    )
            except Exception:
                pass
            else:
                raise AssertionError(
                    f'Убедитесь, что функция `{func_name}` выбрасывает '
                    'исключение, когда API домашки '
                    'возвращает недокументированный '
                    'статус домашней работы либо домашку без статуса.'
                )

    def test_parse_status_no_homework_name_key(self, homework_module):
        homework_with_invalid_name = {
            'status': 'approved'
        }
        func_name = 'parse_status'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        try:
            homework_module.parse_status(homework_with_invalid_name)
        except KeyError as e:
            if repr(e) == "KeyError('homework_name')":
                raise AssertionError(
                    f'Убедитесь, что функция `{func_name}` выбрасывает '
                    'исключение с понятным текстом ошибки, когда в ответе '
                    'API домашки нет ключа `homework_name`.'
                )
        except Exception:
            pass
        else:
            raise AssertionError(
                f'Убедитесь, что функция `{func_name}` выбрасывает '
                'исключение, когда в ответе API домашки нет ключа '
                '`homework_name`.'
            )

    def test_check_response(self, random_timestamp, homework_module):
        func_name = 'check_response'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        valid_response = {
            'homeworks': [
                {
                    'homework_name': 'hw123',
                    'status': 'approved'
                }
            ],
            'current_date': random_timestamp
        }
        try:
            homework_module.check_response(valid_response)
        except Exception as e:
            raise AssertionError(
                'Убедитесь, что при корректном ответе API функция '
                f'`{func_name}` не вызывает исключений.'
            ) from e

    @pytest.mark.parametrize('response', INVALID_RESPONSES.values())
    def test_check_invalid_response(self, response, homework_module):
        func_name = 'check_response'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        if response.defected_key:
            try:
                homework_module.check_response(response.data)
            except KeyError as e:
                if repr(e) == f"KeyError('{response.defected_key}')":
                    raise AssertionError(
                        f'Убедитесь, что функция `{func_name}` выбрасывает '
                        'исключение, если в ответе API домашки нет ключа '
                        f'`{response.defected_key}`.'
                    ) from e
            except Exception:
                pass
            else:
                raise AssertionError(
                    f'Убедитесь, что функция `{func_name}` выбрасывает '
                    'исключение, если в ответе API домашки нет ключа '
                    f'`{response.defected_key}`.'
                )
        else:
            assert_message = (
                f'Убедитесь, что функция `{func_name}` выбрасывает исключение '
                '`TypeError`, если в ответе API домашки '
                'под ключом `homeworks` '
                'данные приходят не в виде списка.'
            )
            if isinstance(response.data, list):
                assert_message = (
                    f'Убедитесь, что функция `{func_name}` выбрасывает '
                    'исключение `TypeError` в случае, если в ответе API '
                    'структура данных не соответствует ожиданиям: например, '
                    'получен список вместо ожидаемого словаря.'
                )
            try:
                homework_module.check_response(response.data)
            except TypeError:
                pass
            except Exception:
                raise AssertionError(assert_message)
            else:
                raise AssertionError(assert_message)

    def test_send_message(
            self, monkeypatch, random_message, caplog, homework_module
    ):
        monkeypatch.setattr(homework_module, 'PRACTICUM_TOKEN', 'sometoken')
        monkeypatch.setattr(homework_module, 'TELEGRAM_TOKEN', '1234:abcdefg')
        monkeypatch.setattr(homework_module, 'TELEGRAM_CHAT_ID', '12345')

        func_name = 'send_message'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        bot = get_mock_telegram_bot(monkeypatch, random_message)

        with check_utils.check_logging(caplog, level=logging.DEBUG, message=(
                'Убедитесь, что при успешной отправке сообщения в Telegram '
                'событие логируется с уровнем `DEBUG`.'
        )):
            homework_module.send_message(bot, 'Test_message_check')
            assert bot.chat_id, (
                'Проверьте, что при отправке сообщения бота '
                'передан параметр `chat_id`.'
            )
            assert bot.text, (
                'Проверьте, что при отправке сообщения бота '
                'передан параметр `text`.'
            )
            assert bot.is_message_sent, (
                'Убедитесь, что для отправки сообщения в Telegram применён '
                'метод бота `send_message`.'
            )

    def test_bot_initialized_in_main(self, homework_module):
        func_name = 'main'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        main_source = check_utils.get_clean_source_code(
            inspect.getsource(homework_module.main)
        )
        bot_init_pattern = re.compile(
            r'(\w* ?= ?)((telebot\.)?TeleBot\(\s*[\w=_\-\'\"]*\s*\))'
        )
        search_result = re.search(bot_init_pattern, main_source)
        assert search_result, (
            'Убедитесь, что бот инициализируется только в функции `main()`.'
        )

        bot_init_with_token_pattern = re.compile(
            r'TeleBot\(\s*(token)?\s*=?\s*TELEGRAM_TOKEN\s*\)'
        )
        assert re.search(bot_init_with_token_pattern, main_source), (
            'Убедитесь, что при создании бота в него передан токен: '
            '`token=TELEGRAM_TOKEN`.'
        )

    def mock_main(
            self, monkeypatch, random_message, random_timestamp,
            current_timestamp, homework_module, mock_bot=True,
            response_data=None
    ):
        """
        Mock all functions inside main() which need environment vars to work
        correctly.
        """
        monkeypatch.setattr(homework_module, 'PRACTICUM_TOKEN', 'sometoken')
        monkeypatch.setattr(homework_module, 'TELEGRAM_TOKEN', '1234:abcdefg')
        monkeypatch.setattr(homework_module, 'TELEGRAM_CHAT_ID', '12345')

        func_name = 'main'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        main_source = check_utils.get_clean_source_code(
            inspect.getsource(homework_module.main)
        )

        time_sleep_pattern = re.compile(
            r'(\# *)?(time\.sleep\( *[\w\d=_\-\'\"]* *\))'
        )
        search_result = re.search(time_sleep_pattern, main_source)
        assert search_result, (
            'Убедитесь, что в `main()` применена функция `time.sleep()`.'
        )

        def sleep_to_interrupt(secs):
            caller = inspect.stack()[1].function
            if caller != 'main':
                old_sleep(secs)
                return
            assert secs == 600, (
                'Убедитесь, что повторный запрос к API домашки отправляется '
                'через 10 минут: `time.sleep(RETRY_PERIOD)`.'
            )
            raise check_utils.BreakInfiniteLoop('break')

        monkeypatch.setattr(time, 'sleep', sleep_to_interrupt)
        if mock_bot:
            def mock_telegram_bot(random_message=random_message, *args,
                                  **kwargs):
                return check_utils.MockTelegramBot(
                    *args,
                    message=random_message,
                    **kwargs
                )

            monkeypatch.setattr(telebot, 'TeleBot', mock_telegram_bot)
            if hasattr(homework_module, 'TeleBot'):
                monkeypatch.setattr(
                    homework_module, 'TeleBot', mock_telegram_bot
                )

        func_name = 'get_api_answer'
        check_utils.check_function(
            homework_module,
            func_name,
            self.HOMEWORK_FUNC_WITH_PARAMS_QTY[func_name]
        )

        mock_response_get_with_new_status = (
            create_mock_response_get_with_custom_status_and_data(
                random_timestamp=random_timestamp,
                http_status=HTTPStatus.OK,
                data=response_data
            ))
        monkeypatch.setattr(
            requests,
            'get',
            mock_response_get_with_new_status
        )
        if platform.system() != 'Windows':
            homework_module.main = (
                check_utils.with_timeout(homework_module.main)
            )

    def test_main_without_env_vars_raise_exception(
            self, caplog, monkeypatch, random_timestamp, current_timestamp,
            random_message, homework_module
    ):
        self.mock_main(
            monkeypatch,
            random_message,
            random_timestamp,
            current_timestamp,
            homework_module
        )
        monkeypatch.setattr(homework_module, 'PRACTICUM_TOKEN', None)
        monkeypatch.setattr(homework_module, 'TELEGRAM_TOKEN', None)
        monkeypatch.setattr(homework_module, 'TELEGRAM_CHAT_ID', None)
        with check_utils.check_logging(
            caplog, level=logging.CRITICAL,
            message=(
                'Убедитесь, что при отсутствии обязательных переменных '
                'окружения событие логируется с уровнем `CRITICAL`.'
            )
        ):
            try:
                homework_module.main()
            except check_utils.BreakInfiniteLoop:
                raise AssertionError(
                    'Убедитесь, что при запуске бота без переменных окружения '
                    'программа принудительно останавливается.'
                )
            except (Exception, SystemExit):
                pass

    def test_main_send_request_to_api(
            self, monkeypatch, random_timestamp, current_timestamp,
            random_message, caplog, homework_module
    ):
        self.mock_main(
            monkeypatch,
            random_message,
            random_timestamp,
            current_timestamp,
            homework_module
        )

        with caplog.at_level(logging.WARN):
            try:
                homework_module.main()
            except check_utils.BreakInfiniteLoop:
                log_record = [
                    record for record in caplog.records
                    if record.message == (
                        check_utils.MockResponseGET.CALLED_LOG_MSG
                    )
                ]
                assert log_record, (
                    'Убедитесь, что бот использует функцию `requests.get()` '
                    'для отправки запроса к API домашки.'
                )

    def test_main_check_response_is_called(
            self, monkeypatch, random_timestamp, current_timestamp,
            random_message, caplog, homework_module
    ):
        self.mock_main(
            monkeypatch,
            random_message,
            random_timestamp,
            current_timestamp,
            homework_module
        )

        func_name = 'check_response'
        expecred_data = {
            "homeworks": [],
            "current_date": random_timestamp
        }
        log_msg = 'Call check_response'
        no_response_assert_msg = (
            f'Убедитесь, что в функцию `{func_name}` передан ответ API '
            'домашки.'
        )

        def mock_check_response(response=None):
            if response != expecred_data:
                raise SystemExit(no_response_assert_msg)
            logging.warn(log_msg)

        monkeypatch.setattr(
            homework_module,
            func_name,
            mock_check_response
        )
        with caplog.at_level(logging.WARN):
            try:
                homework_module.main()
            except SystemExit:
                raise AssertionError(no_response_assert_msg)
            except check_utils.BreakInfiniteLoop:
                log_records = [
                    record for record in caplog.records
                    if record.message in (log_msg, no_response_assert_msg)
                ]
                assert log_records, (
                    'Убедитесь, что для проверки ответа API домашки '
                    f'бот использует функцию `{func_name}`.'
                )

    def test_main_send_message_with_new_status(
            self, monkeypatch, random_timestamp, current_timestamp,
            random_message, caplog, homework_module, data_with_new_hw_status
    ):
        self.mock_main(
            monkeypatch,
            random_message,
            random_timestamp,
            current_timestamp,
            homework_module,
            response_data=data_with_new_hw_status
        )

        hw_status = data_with_new_hw_status['homeworks'][0]['status']

        def mock_send_message(bot, message=''):
            logging.warn(message)

        monkeypatch.setattr(
            homework_module,
            'send_message',
            mock_send_message
        )
        with caplog.at_level(logging.WARN):
            try:
                homework_module.main()
            except check_utils.BreakInfiniteLoop:
                log_record = [
                    record.message for record in caplog.records
                    if self.HOMEWORK_VERDICTS[hw_status] in record.message
                ]
                assert log_record, (
                    'Убедитесь, что при изменении статуса домашней работы '
                    'бот отправляет в Telegram сообщение с вердиктом '
                    'из переменной `HOMEWORK_VERDICTS`.'
                )
            except (Exception, SystemExit) as e:
                raise AssertionError(
                    f'Вызов функции `main` завершился ошибкой: {e}'
                ) from e

    def test_main_log_response_whithout_homeworks(
            self, monkeypatch, random_timestamp, current_timestamp,
            random_message, caplog, homework_module
    ):
        self.mock_main(
            monkeypatch,
            random_message,
            random_timestamp,
            current_timestamp,
            homework_module
        )
        with caplog.at_level(logging.DEBUG):
            try:
                homework_module.main()
            except check_utils.BreakInfiniteLoop:
                log_records = [
                    record.message for record in caplog.records
                    if record.levelno == logging.DEBUG
                ]
                assert log_records, (
                    'Убедитесь, что, если в ответе API получен пустой список '
                    'домашних работ, бот логирует отсутствие изменения '
                    'статуса сообщением с уровнем `DEBUG`.'
                )
            except (Exception, SystemExit) as e:
                raise AssertionError(
                    f'Вызов функции `main` завершился ошибкой: {e}'
                ) from e

    def test_main_send_message_with_telegram_exception(
            self, monkeypatch, random_timestamp, current_timestamp,
            random_message, caplog, homework_module, data_with_new_hw_status
    ):
        self.mock_main(
            monkeypatch,
            random_message,
            random_timestamp,
            current_timestamp,
            homework_module,
            mock_bot=False,
            response_data=data_with_new_hw_status
        )

        class MockedBotWithException(check_utils.MockTelegramBot):
            def send_message(self, *args, **kwargs):
                raise telebot.apihelper.ApiException(
                    'Произошла ошибка при отправке сообщения в Telegram.',
                    'send_message',
                    500
                )

        monkeypatch.setattr(telebot, 'TeleBot', MockedBotWithException)
        if hasattr(homework_module, 'TeleBot'):
            monkeypatch.setattr(
                homework_module, 'TeleBot', MockedBotWithException
            )

        with check_utils.check_logging(caplog, level=logging.ERROR, message=(
                'Убедитесь, что ошибка отправки сообщения в Telegram '
                'логируется с уровнем `ERROR`.'
        )):
            try:
                homework_module.main()
            except check_utils.BreakInfiniteLoop:
                pass
            except (Exception, SystemExit) as e:
                raise AssertionError(
                    'Убедитесь, что бот не останавливает работу при '
                    'возникновении ошибки отправки сообщения в Телеграм.'
                ) from e

    def test_docstrings(self, homework_module):
        for func in self.HOMEWORK_FUNC_WITH_PARAMS_QTY:
            check_utils.check_docstring(homework_module, func)
