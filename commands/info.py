import logging
from state.manager import StateManager, BusyState
from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


async def handle_info(
    command: str,
    args: str,
    chat_id: str,
    event,
    state: StateManager,
    sender: ChannelSender,
) -> None:
    """Обработчик команды /info — показывает скорость токенов, модель и размер контекста."""
    health_ok = await state.is_health_ok()
    prompt_tps, generation_tps = await state.get_metrics()
    model_name = await state.get_model_name()
    context_size = await state.get_context_size()
    busy_state = await state.get_busy_state()

    if not health_ok:
        status_line = "❌ LLM не доступна (отключена)"
    elif busy_state == BusyState.BUSY:
        status_line = "⏳ LLM занята"
    else:
        status_line = "✅ LLM свободна"

    response = (
        f"{status_line}\n"
        f"📊 Скорость токенов:\n"
        f"  Prompt: {prompt_tps:.1f} tok/s\n"
        f"  Generation: {generation_tps:.1f} tok/s\n"
        f"🤖 Модель: {model_name}\n"
        f"📏 Размер контекстного окна: {context_size}"
    )
    await sender.send(response)
