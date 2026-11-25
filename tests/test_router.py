"""Тесты для CommandRouter."""
import asyncio
import pytest

from commands.router import CommandRouter


pytestmark = pytest.mark.asyncio


class TestRegisterAndCall:
    """Тесты регистрации и вызова команд."""

    async def test_register_and_invoke_handler(self):
        """Регистрация и вызов известной команды."""
        router = CommandRouter()
        results = []

        async def handler(command, args, chat_id, event):
            results.append((command, args, chat_id))

        router.register("test", handler)
        event = None
        result = await router.handle("/test", "chat123", event)

        assert result is True
        assert len(results) == 1
        assert results[0] == ("test", "", "chat123")

    async def test_handler_receives_args(self):
        """Обработчик получает аргументы из текста."""
        router = CommandRouter()
        received_args = []

        async def handler(command, args, chat_id, event):
            received_args.append(args)

        router.register("echo", handler)
        await router.handle("/echo hello world", "chat1", None)
        assert received_args == ["hello world"]

    async def test_handler_is_sync_function(self):
        """Синхронный обработчик также вызывается."""
        router = CommandRouter()
        called = []

        def sync_handler(command, args, chat_id, event):
            called.append(True)

        router.register("sync", sync_handler)
        await router.handle("/sync", "chat1", None)
        assert called == [True]


class TestUnknownCommand:
    """Тесты обработки неизвестных команд."""

    async def test_unknown_command_does_not_raise(self):
        """Неизвестная команда не вызывает исключение."""
        router = CommandRouter()
        result = await router.handle("/unknown_command", "chat1", None)
        assert result is True

    async def test_non_command_returns_false(self):
        """Обычное сообщение (не команда) возвращает False."""
        router = CommandRouter()
        result = await router.handle("просто текст", "chat1", None)
        assert result is False

    async def test_empty_text_returns_false(self):
        """Пустой текст возвращает False."""
        router = CommandRouter()
        result = await router.handle("", "chat1", None)
        assert result is False


class TestErrorHandler:
    """Тесты обработки ошибок в обработчиках."""

    async def test_handler_exception_does_not_break_router(self):
        """Ошибка в обработчике не ломает роутер."""
        router = CommandRouter()

        async def failing_handler(command, args, chat_id, event):
            raise ValueError("Тестовая ошибка")

        router.register("fail", failing_handler)
        # Не должно выбросить исключение
        result = await router.handle("/fail", "chat1", None)
        assert result is True

    async def test_router_works_after_handler_exception(self):
        """Роутер продолжает работать после ошибки в обработчике."""
        router = CommandRouter()
        call_count = []

        async def failing_handler(command, args, chat_id, event):
            raise RuntimeError("Ошибка")

        async def good_handler(command, args, chat_id, event):
            call_count.append(1)

        router.register("fail", failing_handler)
        router.register("good", good_handler)

        await router.handle("/fail", "chat1", None)
        assert len(call_count) == 0

        await router.handle("/good", "chat1", None)
        assert len(call_count) == 1


class TestParsing:
    """Тесты парсинга аргументов."""

    async def test_parsing_command_with_single_arg(self):
        """Парсинг команды с одним аргументом."""
        router = CommandRouter()
        captured = []

        async def handler(command, args, chat_id, event):
            captured.append(args)

        router.register("cmd", handler)
        await router.handle("/cmd singlearg", "chat1", None)
        assert captured == ["singlearg"]

    async def test_parsing_command_with_multiple_args(self):
        """Парсинг команды с несколькими аргументами."""
        router = CommandRouter()
        captured = []

        async def handler(command, args, chat_id, event):
            captured.append(args)

        router.register("cmd", handler)
        await router.handle("/cmd arg1 arg2 arg3", "chat1", None)
        assert captured == ["arg1 arg2 arg3"]

    async def test_command_case_insensitive(self):
        """Команды регистронезависимы."""
        router = CommandRouter()
        called = []

        async def handler(command, args, chat_id, event):
            called.append(True)

        router.register("STATUS", handler)
        await router.handle("/status", "chat1", None)
        assert called == [True]

    async def test_command_with_leading_spaces(self):
        """Команда с ведущими пробелами."""
        router = CommandRouter()
        called = []

        async def handler(command, args, chat_id, event):
            called.append(True)

        router.register("trim", handler)
        await router.handle("  /trim  args  ", "chat1", None)
        assert called == [True]
