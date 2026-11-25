"""Тесты для StateManager."""
import asyncio
import pytest

from state.manager import StateManager, BusyState


pytestmark = pytest.mark.asyncio


class TestInitialState:
    """Тесты начального состояния."""

    async def test_initial_busy_state_is_unknown(self, state_manager: StateManager):
        """Начальное состояние занятости — UNKNOWN."""
        state = await state_manager.get_busy_state()
        assert state == BusyState.UNKNOWN

    async def test_initial_processing_count_is_zero(self, state_manager: StateManager):
        """Начальный processing_count — 0."""
        assert state_manager._processing_count == 0

    async def test_initial_model_name_is_default(self, state_manager: StateManager):
        """Начальное название модели — 'неизвестно'."""
        name = await state_manager.get_model_name()
        assert name == "неизвестно"

    async def test_initial_context_size_is_zero(self, state_manager: StateManager):
        """Начальный размер контекста — 0."""
        ctx = await state_manager.get_context_size()
        assert ctx == 0

    async def test_initial_health_is_false(self, state_manager: StateManager):
        """Начальное состояние здоровья — False."""
        health = await state_manager.is_health_ok()
        assert health is False


class TestProcessingCount:
    """Тесты update_processing_count."""

    async def test_count_one_sets_busy(self, state_manager: StateManager):
        """update_processing_count(1) → состояние BUSY."""
        result = await state_manager.update_processing_count(1, stability_timeout=5)
        assert result == BusyState.BUSY
        state = await state_manager.get_busy_state()
        assert state == BusyState.BUSY

    async def test_count_zero_starts_stability_timer(self, state_manager: StateManager):
        """update_processing_count(0) запускает таймер стабильности."""
        # Сначала установим BUSY
        await state_manager.update_processing_count(1, stability_timeout=1)
        assert await state_manager.get_busy_state() == BusyState.BUSY

        # Теперь count=0 — таймер запускается, но состояние ещё BUSY
        result = await state_manager.update_processing_count(0, stability_timeout=0.1)
        assert result is None  # состояние пока не изменилось
        assert await state_manager.get_busy_state() == BusyState.BUSY

        # Ждём таймер
        await asyncio.sleep(0.15)
        state = await state_manager.get_busy_state()
        assert state == BusyState.FREE

    async def test_stability_timer_transitions_to_free(self, state_manager: StateManager):
        """После STABILITY_TIMEOUT состояние становится FREE."""
        await state_manager.update_processing_count(1, stability_timeout=1)
        await state_manager.update_processing_count(0, stability_timeout=0.1)
        await asyncio.sleep(0.15)
        state = await state_manager.get_busy_state()
        assert state == BusyState.FREE

    async def test_canceling_stability_timer_does_not_break_state(self, state_manager: StateManager):
        """Отмена таймера не ломает состояние."""
        # Запускаем в BUSY
        await state_manager.update_processing_count(1, stability_timeout=1)

        # count=0, таймер запускается
        await state_manager.update_processing_count(0, stability_timeout=1.0)
        assert await state_manager.get_busy_state() == BusyState.BUSY

        # Снова count=1 — таймер должен отмениться, состояние BUSY
        result = await state_manager.update_processing_count(1, stability_timeout=1)
        assert result == BusyState.BUSY
        assert await state_manager.get_busy_state() == BusyState.BUSY

        # Проверяем, что таймер очищен
        assert state_manager._free_stable_timer is None

    async def test_multiple_count_zero_calls_reuse_timer(self, state_manager: StateManager):
        """Повторные вызовы с count=0 не запускают новый таймер."""
        await state_manager.update_processing_count(1, stability_timeout=1)
        await state_manager.update_processing_count(0, stability_timeout=0.1)

        first_timer = state_manager._free_stable_timer
        assert first_timer is not None

        # Второй вызов — таймер тот же
        await state_manager.update_processing_count(0, stability_timeout=0.1)
        assert state_manager._free_stable_timer is first_timer


class TestModelInfo:
    """Тесты set_model_info."""

    async def test_set_model_info(self, state_manager: StateManager):
        """set_model_info() устанавливает модель и контекст."""
        await state_manager.set_model_info("llama-3.1-8b", 8192)
        name = await state_manager.get_model_name()
        ctx = await state_manager.get_context_size()
        assert name == "llama-3.1-8b"
        assert ctx == 8192


class TestGetState:
    """Тесты get_state() — сбор полного состояния."""

    async def test_health_state_reflects_updates(self, state_manager: StateManager):
        """set_health_ok() корректно меняет состояние."""
        assert await state_manager.is_health_ok() is False
        await state_manager.set_health_ok(True)
        assert await state_manager.is_health_ok() is True
        await state_manager.set_health_ok(False)
        assert await state_manager.is_health_ok() is False


class TestMetrics:
    """Тесты метрик."""

    async def test_set_and_get_metrics(self, state_manager: StateManager):
        """set_metrics() и get_metrics() работают корректно."""
        await state_manager.set_metrics(10.5, 25.3)
        prompt_tps, gen_tps = await state_manager.get_metrics()
        assert prompt_tps == 10.5
        assert gen_tps == 25.3

    async def test_initial_metrics_are_zero(self, state_manager: StateManager):
        """Начальные метрики — 0."""
        prompt_tps, gen_tps = await state_manager.get_metrics()
        assert prompt_tps == 0.0
        assert gen_tps == 0.0
