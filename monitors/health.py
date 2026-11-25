import asyncio
import logging
import time
from typing import TYPE_CHECKING

from monitors.base import BaseMonitor
from utils.http_client import HTTPClient
from state.manager import StateManager

if TYPE_CHECKING:
    from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


class HealthMonitor(BaseMonitor):
    """Монитор здоровья LLM — проверяет /health endpoint."""

    def __init__(
        self,
        http: HTTPClient,
        state: StateManager,
        sender: "ChannelSender",
        check_interval: float,
        cooldown_period: int,
    ):
        self.http = http
        self.state = state
        self.sender = sender
        self.check_interval = check_interval
        self.cooldown_period = cooldown_period
        self._last_notification_time: float = 0

    async def tick(self) -> None:
        """Проверить /health и отправить уведомление если состояние изменилось."""
        try:
            text = await self.http.get("/health")
            is_ok = "ok" in text.lower()

        except Exception as e:
            logger.warning("Не удалось проверить /health: %s", e)
            is_ok = False

        # Обновляем состояние
        current_health = await self.state.is_health_ok()

        if is_ok and not current_health:
            # LLM восстановилась
            await self.state.set_health_ok(True)
            await self.sender.send("✅ LLM доступна")

        elif not is_ok and current_health:
            # LLM только что стала недоступна
            await self.state.set_health_ok(False)
            await self.sender.send("❌ LLM не доступна (отключена)")
            self._last_notification_time = time.monotonic()

        elif not is_ok and not current_health:
            # LLM по-прежнему недоступна — повторяем с кулдауном
            now = time.monotonic()
            if now - self._last_notification_time >= self.cooldown_period:
                await self.sender.send("❌ LLM не доступна (отключена)")
                self._last_notification_time = now
