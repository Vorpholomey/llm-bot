import logging
from state.manager import StateManager
from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


async def handle_health(
    command: str,
    args: str,
    chat_id: str,
    event,
    state: StateManager,
    sender: ChannelSender,
) -> None:
    """Обработчик команды /health — показывает статус здоровья LLM."""
    is_ok = await state.is_health_ok()
    if is_ok:
        response = "✅ LLM здорова (доступна)"
    else:
        response = "❌ LLM не доступна (отключена)"
    await sender.send(response)
