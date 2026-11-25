import logging
from state.manager import StateManager, BusyState
from botcore.sender import ChannelSender

logger = logging.getLogger(__name__)


async def handle_status(
    command: str,
    args: str,
    chat_id: str,
    event,
    state: StateManager,
    sender: ChannelSender,
) -> None:
    """Обработчик команды /status — показывает текущий статус занятости LLM."""
    busy_state = await state.get_busy_state()

    if busy_state == BusyState.BUSY:
        response = "⏳ LLM занята (обрабатывает запрос)"
    elif busy_state == BusyState.FREE:
        response = "✅ LLM свободна"
    else:
        response = "❓ Состояние LLM неизвестно"

    await sender.send(response)
