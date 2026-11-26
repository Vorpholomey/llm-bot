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
        # На первом тике также вызывается /models для загрузки информации о модели
        async def mock_get(path: str):
            if path == "/health":
                return '{"status": "ok"}'
            elif path == "/models":
                return '{"data": [{"id": "test-model", "meta": {"n_ctx": 4096}}]}'
            return "{}"

        http_client_mock.get.side_effect = mock_get

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        await monitor.tick()

        # Проверка: /health и /models были вызваны (на первом тике модель загружается)
        assert http_client_mock.get.call_count == 2
        http_client_mock.get.assert_any_call("/health")
        http_client_mock.get.assert_any_call("/models")

        # Состояние здоровья — OK
        assert await state_manager.is_health_ok() is True

        # Отправлено сообщение с force=True
        sender_mock.send.assert_called_once_with("✅ LLM доступна", force=True)

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

        # Отправлено сообщение об ошибке с force=True
        sender_mock.send.assert_called_once_with("❌ LLM не доступна (отключена)", force=True)

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
        sender_mock.send.assert_called_once_with("❌ LLM не доступна (отключена)", force=True)


class TestCooldown:
    """Тесты кулдауна уведомлений."""

    async def test_cooldown_prevents_repeat_messages(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Повторные сообщения о недоступности НЕ отправляются."""
        http_client_mock.get.return_value = '{"status": "error"}'

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=60,
        )

        # Имитируем, что первое уведомление уже было отправлено
        monitor._notified_unavailable = True

        # Тик — сообщение не должно отправиться
        await monitor.tick()
        assert sender_mock.send.call_count == 0

        # Ещё один тик — тоже ничего
        await monitor.tick()
        assert sender_mock.send.call_count == 0

    async def test_no_repeat_notifications_when_llm_unavailable(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """Пока LLM недоступна, повторные сообщения НЕ отправляются."""
        http_client_mock.get.return_value = '{"status": "error"}'

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=60,
        )

        # Имитируем, что первое уведомление уже было отправлено
        monitor._notified_unavailable = True

        # Несколько тиков — сообщения не должны отправляться
        await monitor.tick()
        assert sender_mock.send.call_count == 0

        await monitor.tick()
        assert sender_mock.send.call_count == 0

        await monitor.tick()
        assert sender_mock.send.call_count == 0

    async def test_sends_notification_on_startup_when_backend_down(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """При старте с отключённым бэкэндом — уведомление отправляется."""
        http_client_mock.get.side_effect = Exception("Connection refused")

        # health_ok по умолчанию False — бэкэнд уже "недоступен"
        assert await state_manager.is_health_ok() is False

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )
        # _last_notification_time = time.monotonic() - cooldown_period, кулдаун истёк

        await monitor.tick()

        # Уведомление отправлено с force=True
        sender_mock.send.assert_called_once_with(
            "❌ LLM не доступна (отключена)", force=True
        )

    async def test_flapping_respects_cooldown(
        self, state_manager: StateManager, http_client_mock, sender_mock
    ):
        """При мигании (OK→ERROR→OK→ERROR) кулдаун предотвращает спам."""
        # Сценарий: OK, ERROR, OK, ERROR, OK, ERROR
        responses = ["ok", "error", "ok", "error", "ok", "error"]
        call_index = 0

        async def mock_get(path):
            nonlocal call_index
            if path == "/health":
                result = responses[call_index]
                call_index += 1
                return f'{{"status": "{result}"}}'
            return "{}"

        http_client_mock.get.side_effect = mock_get

        monitor = HealthMonitor(
            http=http_client_mock,
            state=state_manager,
            sender=sender_mock,
            check_interval=30,
            cooldown_period=300,
        )

        # 6 тиков
        for _ in range(6):
            await monitor.tick()

        # Сообщение об ошибке отправлено только 1 раз (при первом переходе OK→ERROR)
        # Последующие переходы OK→ERROR пропущены из-за кулдауна
        error_calls = [
            c for c in sender_mock.send.call_args_list
            if "не доступна" in str(c)
        ]
        ok_calls = [
            c for c in sender_mock.send.call_args_list
            if "доступна" in str(c) and "не" not in str(c)
        ]

        assert len(error_calls) == 1, f"Ожидается 1 сообщение об ошибке, получено {len(error_calls)}"
        assert len(ok_calls) == 3, f"Ожидается 3 сообщения 'доступна', получено {len(ok_calls)}"


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
