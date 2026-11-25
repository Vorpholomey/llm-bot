import asyncio
import json
import logging
from typing import Optional
from httpx import AsyncClient, Timeout

logger = logging.getLogger(__name__)


class HTTPClient:
    """Асинхронный HTTP клиент для запросов к LLM API с retry."""

    def __init__(self, base_url: str, timeout: int = 5, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = Timeout(timeout)
        self.retries = retries
        self._client: Optional[AsyncClient] = None

    async def __aenter__(self):
        self._client = AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
        self._client = None

    async def get(self, path: str) -> str:
        """Выполнить GET запрос с retry и вернуть текст ответа."""
        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(1, self.retries + 1):
            try:
                if self._client is None:
                    raise RuntimeError("HTTPClient not initialized. Use async context manager.")
                response = await self._client.get(url)
                response.raise_for_status()
                return response.text
            except Exception as e:
                last_error = e
                wait_time = 2 ** (attempt - 1) * 0.5  # exponential backoff: 0.5, 1, 2
                logger.warning(
                    "Запрос к %s попытка %d/%d: %s. Повтор через %.1f сек",
                    url, attempt, self.retries, e, wait_time
                )
                await asyncio.sleep(wait_time)

        raise last_error  # type: ignore[misc]

    async def get_json(self, path: str) -> dict:
        """
        Выполнить GET запрос с retry и вернуть JSON ответ.

        Включает валидацию: проверяет что ответ не пустой и содержит
        валидный JSON перед попыткой парсинга. При JSONDecodeError
        логирует диагностическую информацию и повторяет запрос.
        """
        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(1, self.retries + 1):
            try:
                if self._client is None:
                    raise RuntimeError("HTTPClient not initialized. Use async context manager.")
                response = await self._client.get(url)
                response.raise_for_status()

                # Валидация: проверяем что тело ответа не пустое
                body = response.text.strip()
                if not body:
                    logger.warning(
                        "Пустой ответ от %s (status=%s), попытка %d/%d",
                        url, response.status_code, attempt, self.retries
                    )
                    raise ValueError(f"Пустой ответ от {url}")

                # Валидация: проверяем что контент похож на JSON
                if not body.startswith(("{", "[")):
                    logger.warning(
                        "Ответ от %s не похож на JSON (status=%s, первые 200 символов: %s)",
                        url, response.status_code, body[:200]
                    )
                    raise ValueError(f"Ответ не является JSON: {url}")

                # Безопасный парсинг JSON
                try:
                    return json.loads(body)
                except json.JSONDecodeError as e:
                    logger.warning(
                        "JSONDecodeError при парсинге ответа от %s (status=%s): %s. "
                        "Тело ответа (первые 200 символов): %s",
                        url, response.status_code, e, body[:200]
                    )
                    raise

            except json.JSONDecodeError as e:
                last_error = e
                wait_time = 2 ** (attempt - 1) * 0.5
                logger.warning(
                    "Запрос к %s попытка %d/%d: JSONDecodeError. Повтор через %.1f сек",
                    url, attempt, self.retries, wait_time
                )
                await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                wait_time = 2 ** (attempt - 1) * 0.5
                logger.warning(
                    "Запрос к %s попытка %d/%d: %s. Повтор через %.1f сек",
                    url, attempt, self.retries, e, wait_time
                )
                await asyncio.sleep(wait_time)

        raise last_error  # type: ignore[misc]
