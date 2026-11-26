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
        # Инициализируем так, чтобы первое уведомление о сбое прошло
        # (кулдаун считается от момента последнего уведомления)
        self._last_notification_time: float = time.monotonic() - cooldown_period
        self._tick_count: int = 0
        # Флаг: было ли отправлено уведомление о недоступности (для первого старта)
        self._notified_unavailable: bool = False

    async def _fetch_model_info(self) -> None:
        """Запросить /models и обновить информацию о модели в стейте."""
        try:
            raw_text = await self.http.get("/models")
            import json
            data = json.loads(raw_text)
        except Exception as e:
            logger.warning("Не удалось получить /models: %s", e)
            return

        # Пытаемся извлечь название модели и размер контекста
        # Поддерживаем несколько форматов ответа llama.cpp API
        model_name = None
        context_size = 0

        # Формат llama.cpp API: {"data": [{"id": "...", "meta": {"n_ctx": ...}}]}
        if isinstance(data, dict) and "data" in data:
            models_list = data["data"]
            if isinstance(models_list, list) and len(models_list) > 0:
                first = models_list[0]
                # Имя модели в поле "id"
                model_name = first.get("id") or first.get("name") or first.get("model")
                # Размер контекста в meta["n_ctx"]
                meta = first.get("meta")
                if isinstance(meta, dict):
                    n_ctx_val = meta.get("n_ctx")
                    n_ctx_train_val = meta.get("n_ctx_train")
                    context_size = n_ctx_val if n_ctx_val else (n_ctx_train_val if n_ctx_train_val else 0)
                # Фоллбэк на прямые поля
                if not context_size:
                    context_size = first.get("context_size") or first.get("ctx_len") or 0

        # Формат 1: {"models": [{"name": "...", ...}]}
        if not model_name and isinstance(data, dict) and "models" in data:
            models = data["models"]
            if isinstance(models, list) and len(models) > 0:
                first = models[0]
                model_name = first.get("name") or first.get("model") or first.get("id")
                context_size = first.get("context_size") or first.get("ctx_len") or 0

        # Формат 2: {"model_name": "...", "ctx_len": ...}
        if not model_name and isinstance(data, dict):
            model_name = data.get("model_name") or data.get("name") or data.get("model")
            context_size = data.get("context_size") or data.get("ctx_len") or data.get("ctx_size") or 0

        if model_name:
            await self.state.set_model_info(str(model_name), int(context_size))
            logger.info("Модель обновлена: %s (ctx=%d)", model_name, context_size)
        else:
            logger.warning("Модель не определена — ни один формат не подошёл")

    async def tick(self) -> None:
        """Проверить /health и отправить уведомление если состояние изменилось."""
        self._tick_count += 1

        try:
            text = await self.http.get("/health")
            is_ok = "ok" in text.lower()
        except Exception as e:
            logger.warning("Не удалось проверить /health: %s", e)
            is_ok = False

        # Получаем текущее состояние
        current_health = await self.state.is_health_ok()
        now = time.monotonic()
        cooldown_elapsed = now - self._last_notification_time

        if is_ok and not current_health:
            # LLM восстановилась
            await self.state.set_health_ok(True)
            await self.sender.send("✅ LLM доступна", force=True)
            self._notified_unavailable = False

        elif not is_ok and current_health:
            # LLM только что стала недоступна — но проверяем кулдаун
            if cooldown_elapsed >= self.cooldown_period:
                await self.state.set_health_ok(False)
                await self.sender.send("❌ LLM не доступна (отключена)", force=True)
                self._last_notification_time = now
                self._notified_unavailable = True
            else:
                await self.state.set_health_ok(False)

        elif not is_ok and not current_health and not self._notified_unavailable:
            # LLM недоступна при старте — отправить первое уведомление
            await self.state.set_health_ok(False)
            await self.sender.send("❌ LLM не доступна (отключена)", force=True)
            self._notified_unavailable = True

        # Обновляем информацию о модели при первом запуске и периодически
        if self._tick_count == 1 or self._tick_count % self._MODEL_REFRESH_INTERVAL == 0:
            await self._fetch_model_info()
