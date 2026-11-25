import logging
from state.manager import StateManager
from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


async def handle_context(
    command: str,
    args: str,
    chat_id: str,
    event,
    state: StateManager,
    sender: ChannelSender,
) -> None:
    """Обработчик команды /context — показывает размер контекстного окна."""
    context_size = await state.get_context_size()
    if context_size > 0:
        response = f"📏 Размер контекстного окна: {context_size} токенов"
    else:
        response = "📏 Информация о контекстном окне недоступна"
    await sender.send(response)
