"""Тесты для HealthMonitor с mock."""
import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from monitors.health import HealthMonitor
from state.manager import StateManager


pytestmark = pytest.mark.asyncio


class TestHealthCheck:
    """Тесты проверки здоровья."""

    async def test_successful_health_check_sends_ok_message(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Успешный ответ /health → статус OK, сообщение отправлено."""
        http_client_mock.get.return_value = '{"status": "ok"}'

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        await monitor.tick()

        # Проверка: /health был вызван
        http_client_mock.get.assert_called_once_with("/health")

        # Состояние здоровья — OK
        assert await state_manager.is_health_ok() is True

        # Отправлено сообщение
        sender_mock.send.assert_called_once_with("✅ LLM доступна")

    async def test_failed_health_check_sends_error_message(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Неудачный ответ /health → статус не OK, сообщение отправлено."""
        http_client_mock.get.return_value = '{"status": "error"}'

        # Сначала установим health OK, чтобы была смена состояния
        await state_manager.set_health_ok(True)

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        await monitor.tick()

        # Состояние здоровья — не OK
        assert await state_manager.is_health_ok() is False

        # Отправлено сообщение об ошибке
        sender_mock.send.assert_called_once_with("❌ LLM не доступна (отключена)")

    async def test_health_exception_sets_not_ok(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Исключение при запросе /health → статус не OK."""
        http_client_mock.get.side_effect = Exception("Connection refused")

        await state_manager.set_health_ok(True)

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        await monitor.tick()

        assert await state_manager.is_health_ok() is False
        sender_mock.send.assert_called_once_with("❌ LLM не доступна (отключена)")


class TestCooldown:
    """Тесты кулдауна уведомлений."""

    async def test_cooldown_prevents_repeat_messages(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Кулдаун предотвращает повторные сообщения о недоступности."""
        http_client_mock.get.return_value = '{"status": "error"}'

        # Установим health=False (начальное состояние) и установим
        # _last_notification_time так, чтобы кулдаун сработал
        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=60,  # 60 секунд кулдаун
        )

        # Установим _last_notification_time в текущее время,
        # чтобы первый тик не отправил сообщение (кулдаун активен)
        monitor._last_notification_time = time.monotonic()

        # Тик — сообщение не должно отправиться (кулдаун)
        await monitor.tick()
        assert sender_mock.send.call_count == 0

        # Ещё один тик — тоже ничего
        await monitor.tick()
        assert sender_mock.send.call_count == 0

    async def test_cooldown_expires_allows_new_message(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """После истечения кулдауна сообщение отправляется снова."""
        http_client_mock.get.return_value = '{"status": "error"}'

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=60,
        )

        # Установим _last_notification_time в прошлое (больше кулдауна назад)
        monitor._last_notification_time = time.monotonic() - 120

        # Первый тик — кулдаун истёк, сообщение отправлено
        await monitor.tick()
        assert sender_mock.send.call_count == 1

        # Второй тик — в кулдауне, сообщение не отправлено
        await monitor.tick()
        assert sender_mock.send.call_count == 1


class TestFetchModelInfo:
    """Тесты _fetch_model_info."""

    async def test_fetch_model_info_failure_does_not_break_monitor(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Недоступный /models не ломает монитор."""
        http_client_mock.get.return_value = '{"status": "ok"}'
        # /models недоступен
        http_client_mock.get.side_effect = Exception("Connection error")

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        # tick должен выполниться без исключения
        await monitor.tick()

    async def test_model_info_updated_after_interval(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Информация о модели обновляется через _MODEL_REFRESH_INTERVAL тиков."""
        import json

        # Первый вызов — /health, второй — /models (на 10-м тике)
        health_response = '{"status": "ok"}'
        models_response = json.dumps({"models": [{"name": "llama-3.1", "context_size": 8192}]})

        async def mock_get(path):
            if path == "/health":
                return health_response
            elif path == "/models":
                return models_response

        http_client_mock.get.side_effect = mock_get

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        # 10 тиков — на 10-м должен быть запрос к /models
        for i in range(10):
            await monitor.tick()

        # Модель должна быть обновлена
        name = await state_manager.get_model_name()
        ctx = await state_manager.get_context_size()
        assert name == "llama-3.1"
        assert ctx == 8192

    async def test_model_info_alternate_format(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Поддержка альтернативного формата ответа /models."""
        import json

        health_response = '{"status": "ok"}'
        models_response = json.dumps({"model_name": "mistral-7b", "ctx_len": 4096})

        async def mock_get(path):
            if path == "/health":
                return health_response
            elif path == "/models":
                return models_response

        http_client_mock.get.side_effect = mock_get

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        for i in range(10):
            await monitor.tick()

        name = await state_manager.get_model_name()
        ctx = await state_manager.get_context_size()
        assert name == "mistral-7b"
        assert ctx == 4096
