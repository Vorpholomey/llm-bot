from abc import ABC, abstractmethod
import asyncio
import logging

logger = logging.getLogger(__name__)


class BaseMonitor(ABC):
    """Базовый абстрактный класс для мониторов."""

    @abstractmethod
    async def tick(self) -> None:
        """Выполнить одну итерацию проверки."""
        pass

    async def run(self, interval: float) -> None:
        """Запустить бесконечный цикл проверок с заданным интервалом."""
        while True:
            try:
                await self.tick()
            except Exception as e:
                logger.error("Ошибка в мониторе %s: %s", self.__class__.__name__, e)
            await asyncio.sleep(interval)
