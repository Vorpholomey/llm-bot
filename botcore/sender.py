import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ChannelSender:
    """Отправка сообщений в канал с дедупликацией."""

    def __init__(self, bot, channel_id: str, dry_run: bool = False):
        self.bot = bot
        self.channel_id = channel_id
        self.dry_run = dry_run
        self._last_message: Optional[str] = None

    async def send(self, text: str) -> None:
        """
        Отправить сообщение в канал.

        Если текст совпадает с предыдущим — сообщение пропускается (дедупликация).
        В режиме dry_run — только логирование.
        """
        if text == self._last_message:
            logger.debug("Дедупликация: сообщение '%s' пропущено", text)
            return

        if self.dry_run:
            logger.info("[DRY RUN] %s", text)
        else:
            try:
                self.bot.send_text(chat_id=self.channel_id, text=text)
                logger.info("Отправлено: %s", text)
            except Exception as e:
                logger.error("Ошибка отправки сообщения: %s", e)

        self._last_message = text
