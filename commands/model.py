import logging
from state.manager import StateManager
from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


async def handle_model(
    command: str,
    args: str,
    chat_id: str,
    event,
    state: StateManager,
    sender: ChannelSender,
) -> None:
    """Обработчик команды /model — показывает название модели."""
    model_name = await state.get_model_name()
    response = f"🤖 Модель: {model_name}"
    await sender.send(response)
