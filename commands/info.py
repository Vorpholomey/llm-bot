import logging
from state.manager import StateManager
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
    prompt_tps, generation_tps = await state.get_metrics()
    model_name = await state.get_model_name()
    context_size = await state.get_context_size()
    response = (
        f"📊 Скорость токенов:\n"
        f"  Prompt: {prompt_tps:.1f} tok/s\n"
        f"  Generation: {generation_tps:.1f} tok/s\n"
        f"🤖 Модель: {model_name}\n"
        f"📏 Размер контекстного окна: {context_size}"
    )
    await sender.send(response)
