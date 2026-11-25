from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения из .env файла."""

    # Бот
    bot_token: str
    channel_id: str

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if v in ("your_bot_token_here", "") or len(v) < 10:
            raise ValueError(
                "BOT_TOKEN не установлен или содержит плейсхолдер. "
                "Укажите реальный токен бота в файле .env"
            )
        return v

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        if v in ("your_channel_id_here", "") or len(v) < 3:
            raise ValueError(
                "CHANNEL_ID не установлен или содержит плейсхолдер. "
                "Укажите реальный ID канала в файле .env"
            )
        return v

    # LLM API
    llm_api_url: str = "http://192.168.1.35:5003"

    # Интервалы (секунды)
    health_check_interval: int = 30
    metrics_check_interval: int = 10
    stability_timeout: int = 10
    cooldown_period: int = 300

    # HTTP
    http_timeout: int = 5
    http_retries: int = 3

    # Dry-run
    dry_run: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def load_settings() -> Settings:
    """Загрузить настройки из .env."""
    return Settings()
