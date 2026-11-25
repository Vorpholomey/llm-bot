"""
Точка входа бота мониторинга LLM для Mail.ru MyTeam.

Запускает:
- Бота (long polling в отдельном потоке через mailru-im-bot)
- Монитор здоровья LLM (/health)
- Монитор метрик LLM (/metrics)
- Обработчик команд
"""

# Полифил cgi для Python 3.13+ — ДО всех импортов, использующих bot
from utils import cgi_compat  # noqa: F401

import asyncio
import logging
import signal
from functools import partial

from config.settings import load_settings
from state.manager import StateManager
from utils.http_client import HTTPClient
from botcore.client import BotClient
from botcore.sender import ChannelSender
from monitors.health import HealthMonitor
from monitors.metrics import MetricsMonitor
from commands.router import CommandRouter

# Импортируем обработчики команд
from commands import status, tokens, model, context, health as health_cmd

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Главная функция — запускает asyncio event loop."""
    settings = load_settings()
    logger.info("Запуск бота мониторинга LLM...")
    logger.info("  LLM API: %s", settings.llm_api_url)
    logger.info("  Канал: %s", settings.channel_id)
    logger.info("  Dry-run: %s", settings.dry_run)

    # Создаём общий event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # State Manager и HTTP Client
    state = StateManager()
    http = HTTPClient(
        base_url=settings.llm_api_url,
        timeout=settings.http_timeout,
        retries=settings.http_retries,
    )

    # Command Router — создаём до on_message, чтобы использовать в замыкании
    router = CommandRouter()

    # Bot Client — колбэк для входящих сообщений
    async def on_message(text: str, chat_id: str, event) -> None:
        """Обработчик входящих сообщений."""
        await router.handle(text, chat_id, event)

    bot_client = BotClient(
        token=settings.bot_token,
        api_url_base="https://myteam.mail.ru/bot/v1",
        callback=lambda text, chat_id, event: loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(on_message(text, chat_id, event))
        ),
        is_myteam=True,
    )

    # Sender
    sender = ChannelSender(
        bot=bot_client.bot,
        channel_id=settings.channel_id,
        dry_run=settings.dry_run,
    )

    # Регистрируем команды (с замыканием state и sender)
    router.register("status", partial(status.handle_status, state=state, sender=sender))
    router.register("tokens", partial(tokens.handle_tokens, state=state, sender=sender))
    router.register("model", partial(model.handle_model, state=state, sender=sender))
    router.register("context", partial(context.handle_context, state=state, sender=sender))
    router.register("health", partial(health_cmd.handle_health, state=state, sender=sender))

    # Мониторы
    health_monitor = HealthMonitor(
        http=http,
        state=state,
        sender=sender,
        check_interval=settings.health_check_interval,
        cooldown_period=settings.cooldown_period,
    )

    metrics_monitor = MetricsMonitor(
        http=http,
        state=state,
        sender=sender,
        check_interval=settings.metrics_check_interval,
        stability_timeout=settings.stability_timeout,
    )

    # Флаг остановки
    stop_event = asyncio.Event()

    # Обработка сигналов остановки
    def signal_handler(sig, frame):
        logger.info("Получен сигнал %s. Остановка...", sig)
        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def run_bot() -> None:
        """
        Запускает polling бота.

        Bot.start_polling() внутри создаёт фоновый поток и сразу возвращает,
        поэтому здесь只需要 запустить и ждать сигнала остановки.
        """
        bot_client.start_polling()
        logger.info("Bot polling запущен")
        await stop_event.wait()
        logger.info("Остановка бота...")
        bot_client.stop()
        logger.info("Бот остановлен")

    async def run_monitors() -> None:
        """Запускает мониторы параллельно."""
        async with http:
            try:
                await asyncio.gather(
                    health_monitor.run(settings.health_check_interval),
                    metrics_monitor.run(settings.metrics_check_interval),
                    return_exceptions=True,
                )
            except asyncio.CancelledError:
                pass

    async def run_all() -> None:
        """Запускает все задачи параллельно."""
        bot_task = asyncio.create_task(run_bot())
        monitors_task = asyncio.create_task(run_monitors())

        # Ждём сигнала остановки
        await stop_event.wait()

        # Отменяем задачи мониторов
        monitors_task.cancel()
        try:
            await monitors_task
        except asyncio.CancelledError:
            pass

        # run_bot остановится сам после stop_event.set()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass

    try:
        loop.run_until_complete(run_all())
    except KeyboardInterrupt:
        logger.info("Остановка по KeyboardInterrupt")
    finally:
        loop.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    main()
