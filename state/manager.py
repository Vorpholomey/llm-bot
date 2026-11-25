import asyncio
import logging
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class BusyState(str, Enum):
    """Состояния занятости LLM."""
    UNKNOWN = "unknown"
    BUSY = "busy"
    FREE = "free"


class StateManager:
    """Менеджер общего состояния (shared state) для мониторов и команд."""

    def __init__(self):
        # Состояние здоровья
        self._health_ok: bool = False

        # Состояние занятости
        self._busy_state: BusyState = BusyState.UNKNOWN

        # Для state machine занятости
        self._processing_count: int = 0  # текущее значение requests_processing
        self._free_stable_timer: Optional[asyncio.Task] = None  # таймер стабильности

        # Метрики
        self._prompt_tokens_per_sec: float = 0.0
        self._generation_tokens_per_sec: float = 0.0
        self._model_name: str = "неизвестно"
        self._context_size: int = 0

        # Блокировка для асинхронной безопасности
        self._lock = asyncio.Lock()

    # --- Health ---

    async def set_health_ok(self, ok: bool) -> None:
        """Установить состояние здоровья."""
        async with self._lock:
            self._health_ok = ok

    async def is_health_ok(self) -> bool:
        """Проверить состояние здоровья."""
        async with self._lock:
            return self._health_ok

    # --- Busy State ---

    async def get_busy_state(self) -> BusyState:
        """Получить текущее состояние занятости."""
        async with self._lock:
            return self._busy_state

    async def _set_busy_state(self, state: BusyState) -> None:
        """Внутренний метод установки состояния (требует lock)."""
        old_state = self._busy_state
        self._busy_state = state
        if old_state != state:
            logger.info("Состояние занятости: %s -> %s", old_state, state)

    async def update_processing_count(self, count: int, stability_timeout: int) -> Optional[BusyState]:
        """
        Обновить счётчик обработки запросов и вернуть новое состояние, если изменилось.

        Логика:
        - count == 1 -> BUSY (сразу)
        - count == 0 -> начать таймер стабильности, по истечении -> FREE
        """
        async with self._lock:
            self._processing_count = count

            if count >= 1:
                # LLM занята — сразу меняем состояние
                if self._free_stable_timer:
                    self._free_stable_timer.cancel()
                    self._free_stable_timer = None
                await self._set_busy_state(BusyState.BUSY)
                return BusyState.BUSY

            else:
                # count == 0 — запускаем таймер стабильности (одноразово)
                if self._busy_state == BusyState.FREE:
                    return None  # уже свободна

                # Только запускаем, если таймер ещё не запущен
                if self._free_stable_timer is None:
                    self._free_stable_timer = asyncio.get_event_loop().create_task(
                        self._stability_delay(stability_timeout)
                    )
                # Если таймер уже запущен — ничего не делаем, позволяем ему течь
                return None

    async def _stability_delay(self, timeout: int) -> None:
        """Задержка стабильности перед переходом в FREE."""
        try:
            await asyncio.sleep(timeout)
            async with self._lock:
                # Проверяем, что после таймаута всё ещё count == 0
                if self._processing_count == 0:
                    # Сбрасываем таймер, чтобы при следующем цикле BUSY->FREE мог запуститься снова
                    self._free_stable_timer = None
                    await self._set_busy_state(BusyState.FREE)
        except asyncio.CancelledError:
            pass  # Таймер был отменён — LLM снова занята

    # --- Metrics ---

    async def set_metrics(self, prompt_tps: float, generation_tps: float) -> None:
        """Установить метрики скорости токенов."""
        async with self._lock:
            self._prompt_tokens_per_sec = prompt_tps
            self._generation_tokens_per_sec = generation_tps

    async def get_metrics(self) -> Tuple[float, float]:
        """Получить метрики скорости токенов."""
        async with self._lock:
            return self._prompt_tokens_per_sec, self._generation_tokens_per_sec

    # --- Model Info ---

    async def set_model_info(self, model_name: str, context_size: int) -> None:
        """Установить информацию о модели."""
        async with self._lock:
            self._model_name = model_name
            self._context_size = context_size

    async def get_model_name(self) -> str:
        """Получить название модели."""
        async with self._lock:
            return self._model_name

    async def get_context_size(self) -> int:
        """Получить размер контекстного окна."""
        async with self._lock:
            return self._context_size
