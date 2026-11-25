"""Полифил модуля cgi для Python 3.13+ (PEP 594).

Пакет mailru-im-bot (v0.0.21) использует cgi.parse_header(), который был
удалён из стандартной библиотеки Python 3.13. Этот модуль предоставляет
совместимую реализацию, чтобы проект мог работать без изменений в site-packages.

Использование:
    from utils import cgi_compat
    cgi_compat.install()  # регистрирует 'cgi' в sys.modules
"""

import re
import sys
import types


def parse_header(line):
    """
    Разпарсить строку MIME-заголовка на значение и словарь параметров.

    Это совместимая реализация cgi.parse_header() для Python 3.13+.

    Аргументы:
        line: Строка заголовка, например "text/html; charset=utf-8"

    Возвращает:
        Кортеж (value, params), где params — словарь параметров.

    Примеры:
        >>> parse_header('text/html; charset=utf-8')
        ('text/html', {'charset': 'utf-8'})
        >>> parse_header('application/json')
        ('application/json', {})
    """
    from email.message import Message

    m = Message()
    m["content-type"] = line

    # get_params() возвращает [('text/html', ''), ('charset', 'utf-8')]
    # Первый кортеж: ключ = MIME-тип, значение = пустая строка
    # Остальные: ключ = имя параметра, значение = значение параметра
    raw_params = m.get_params()
    if not raw_params:
        return line, {}

    # Первый элемент — это основное значение (MIME-тип)
    value = raw_params[0][0]
    params = {k: v for k, v in raw_params[1:]}

    return value, params


def install():
    """
    Зарегистрировать модуль 'cgi' в sys.modules как полифил.

    Вызывайте эту функцию ДО импорта пакетов, использующих cgi.
    """
    if "cgi" in sys.modules:
        return  # уже загружен (Python < 3.13)

    module = types.ModuleType("cgi")
    module.parse_header = parse_header
    sys.modules["cgi"] = module


# Автоматически устанавливаем полифил при импорте
install()
