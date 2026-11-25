"""Обёртка над mailru-im-bot SDK для интеграции с asyncio.

Включает патч для защиты от JSONDecodeError в SDK mailru-im-bot,
который вызывает response.json() без обработки ошибок.
"""

# Полифил cgi для Python 3.13+ — ДО импорта bot
from utils import cgi_compat  # noqa: F401

import json
import logging
from functools import wraps
from bot.bot import Bot as _Bot
from bot.handler import MessageHandler

logger = logging.getLogger(__name__)


def _safe_json_patch():
    """
    Патчит метод .json() объекта Response в SDK mailru-im-bot,
    чтобы добавить обработку JSONDecodeError и диагностическое логирование.

    SDK вызывает response.json() в методах _start_polling() и events_get()
    без какой-либо обработки ошибок. Когда API возвращает пустой ответ
    или не-JSON контент (HTML страница ошибки, пустое тело и т.д.),
    возникает json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0).

    Этот патч перехватывает такие ошибки и возвращает безопасное пустое значение,
    позволяя polling-циклу продолжить работу.
    """
    import requests

    original_json = requests.Response.json

    @wraps(original_json)
    def safe_json(self, *args, **kwargs):
        try:
            return original_json(self, *args, **kwargs)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "SDK mailru-im-bot: JSONDecodeError при парсинге ответа от %s "
                "(status=%s, content-length=%s, error=%s). "
                "Тело ответа (первые 200 символов): %s",
                self.url,
                self.status_code,
                len(self.content),
                e,
                self.text[:200] if self.text else "<пусто>",
            )
            # Возвращаем пустой dict с events=[], чтобы SDK не упал
            # и polling-цикл продолжил работу
            return {"events": []}

    requests.Response.json = safe_json


# Применяем патч при импорте модуля
_safe_json_patch()


class BotClient:
    """Обёртка над mailru-im-bot SDK для интеграции с asyncio."""

    def __init__(self, token: str, api_url_base: str, callback, is_myteam: bool = True):
        self._bot = _Bot(token=token, api_url_base=api_url_base, is_myteam=is_myteam)
        self._callback = callback

        # Регистрируем обработчик всех сообщений
        self._bot.dispatcher.add_handler(MessageHandler(callback=self._on_message))

    @property
    def bot(self) -> _Bot:
        """Доступ к нативному объекту Bot для отправки сообщений."""
        return self._bot

    def _on_message(self, bot, event):
        """Колбэк для входящих сообщений — передаёт в async callback."""
        try:
            text = event.text or ""
            chat_id = event.from_chat
            logger.info("Получено сообщение от %s: %s", chat_id, text)
            self._callback(text, chat_id, event)
        except Exception as e:
            logger.error("Ошибка в обработчике сообщения: %s", e)

    def start_polling(self) -> None:
        """Запустить polling (синхронный, в отдельном потоке)."""
        self._bot.start_polling()

    def stop(self) -> None:
        """Остановить бота."""
        self._bot.stop()
