"""Общие фикстуры для тестов."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from state.manager import StateManager


@pytest.fixture
def state_manager():
    """Создать экземпляр StateManager для тестов."""
    return StateManager()


@pytest.fixture
def http_client_mock():
    """Mock HTTPClient с асинхронными методами."""
    mock = MagicMock()
    mock.get = AsyncMock()
    mock.get_json = AsyncMock()
    return mock


@pytest.fixture
def sender_mock():
    """Mock ChannelSender."""
    mock = MagicMock()
    mock.send = AsyncMock()
    return mock
