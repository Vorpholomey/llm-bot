import asyncio
import logging
import re
from typing import TYPE_CHECKING

from monitors.base import BaseMonitor
from utils.http_client import HTTPClient
from state.manager import StateManager, BusyState

if TYPE_CHECKING:
    from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


class MetricsMonitor(BaseMonitor):
    """Монитор метрик LLM — проверяет /metrics endpoint."""

    # Паттерны для парсинга Prometheus-метрик
    _PATTERN_PROCESSING = re.compile(r"^llamacpp:requests_processing\s+(\d+)$")
    _PATTERN_PROMPT_TPS = re.compile(r"^llamacpp:prompt_tokens_seconds\s+([\d.]+)$")
    _PATTERN_GENERATION_TPS = re.compile(r"^llamacpp:predicted_tokens_seconds\s+([\d.]+)$")

    def __init__(
        self,
        http: HTTPClient,
        state: StateManager,
        sender: "ChannelSender",
        check_interval: float,
        stability_timeout: int,
    ):
        self.http = http
        self.state = state
        self.sender = sender
        self.check_interval = check_interval
        self.stability_timeout = stability_timeout
        self._last_notified_state: BusyState = BusyState.UNKNOWN

    async def tick(self) -> None:
        """Проверить /metrics и обновить состояние занятости."""
        try:
            text = await self.http.get("/metrics")
        except Exception as e:
            logger.warning("Не удалось получить /metrics: %s", e)
            return

        # Парсим метрики
        processing_count = 0
        prompt_tps = 0.0
        generation_tps = 0.0

        for line in text.splitlines():
            line = line.strip()

            match = self._PATTERN_PROCESSING.match(line)
            if match:
                processing_count = int(match.group(1))
                continue

            match = self._PATTERN_PROMPT_TPS.match(line)
            if match:
                prompt_tps = float(match.group(1))
                continue

            match = self._PATTERN_GENERATION_TPS.match(line)
            if match:
                generation_tps = float(match.group(1))
                continue

        # Обновляем метрики скорости
        await self.state.set_metrics(prompt_tps, generation_tps)

        # Обновляем состояние занятости через state machine
        new_state = await self.state.update_processing_count(
            processing_count, self.stability_timeout
        )

        # Получаем актуальное состояние
        current_state = await self.state.get_busy_state()

        # Отправляем уведомление только при смене состояния
        if current_state != self._last_notified_state:
            if current_state == BusyState.BUSY:
                await self.sender.send("⏳ LLM занята")
            elif current_state == BusyState.FREE:
                await self.sender.send("✅ LLM свободна")
            self._last_notified_state = current_state
