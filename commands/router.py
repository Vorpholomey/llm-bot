import asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class CommandRouter:
    """Диспетчер команд — маппинг command_name -> handler."""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, command: str, handler: Callable) -> None:
        """Зарегистрировать обработчик для команды."""
        self._handlers[command.lower()] = handler
        logger.info("Зарегистрирована команда: /%s", command)

    async def handle(self, text: str, chat_id: str, event) -> bool:
        """
        Обработать входящее сообщение как команду.

        Возвращает True, если сообщение было командой и обработано.
        """
        text = text.strip()
        if not text.startswith("/"):
            return False

        # Парсим команду: /command [args]
        parts = text[1:].split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = self._handlers.get(command)
        if handler is None:
            logger.warning("Неизвестная команда: /%s", command)
            return True

        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(command=command, args=args, chat_id=chat_id, event=event)
            else:
                handler(command=command, args=args, chat_id=chat_id, event=event)
        except Exception as e:
            logger.error("Ошибка в обработчике команды /%s: %s", command, e)

        return True
