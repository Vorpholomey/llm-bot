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

    # Обновлять модель раз в ~5 минут (при интервале 30с = 10 тиков)
    _MODEL_REFRESH_INTERVAL = 10

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
        self._tick_count: int = 0

    async def _fetch_model_info(self) -> None:
        """Запросить /models и обновить информацию о модели в стейте."""
        try:
            text = await self.http.get("/models")
            import json
            data = json.loads(text)
        except Exception as e:
            logger.debug("Не удалось получить /models: %s", e)
            return

        # Пытаемся извлечь название модели и размер контекста
        # Поддерживаем несколько форматов ответа llama.cpp API
        model_name = None
        context_size = 0

        # Формат 1: {"models": [{"name": "...", ...}]}
        if isinstance(data, dict) and "models" in data:
            models = data["models"]
            if isinstance(models, list) and len(models) > 0:
                first = models[0]
                model_name = first.get("name") or first.get("model")
                context_size = first.get("context_size") or first.get("ctx_len") or 0

        # Формат 2: {"model_name": "...", "ctx_len": ...}
        if not model_name and isinstance(data, dict):
            model_name = data.get("model_name") or data.get("name") or data.get("model")
            context_size = data.get("context_size") or data.get("ctx_len") or data.get("ctx_size") or 0

        if model_name:
            await self.state.set_model_info(str(model_name), int(context_size))
            logger.info("Модель обновлена: %s (ctx=%d)", model_name, context_size)

    async def tick(self) -> None:
        """Проверить /health и отправить уведомление если состояние изменилось."""
        self._tick_count += 1

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

        # Периодически обновляем информацию о модели
        if self._tick_count % self._MODEL_REFRESH_INTERVAL == 0:
            await self._fetch_model_info()
