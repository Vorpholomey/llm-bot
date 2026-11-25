import logging
from state.manager import StateManager
from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


async def handle_tokens(
    command: str,
    args: str,
    chat_id: str,
    event,
    state: StateManager,
    sender: ChannelSender,
) -> None:
    """Обработчик команды /tokens — показывает скорость токенов."""
    prompt_tps, generation_tps = await state.get_metrics()
    response = (
        f"📊 Скорость токенов:\n"
        f"  Prompt: {prompt_tps:.1f} tok/s\n"
        f"  Generation: {generation_tps:.1f} tok/s"
    )
    await sender.send(response)
