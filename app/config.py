from functools import lru_cache
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import validator
from pydantic_settings import BaseSettings

# Load environment variables from a local .env file if present.
load_dotenv()


class Settings(BaseSettings):
    bot_token: str
    target_chat_id: int
    database_url: str = "sqlite:///./affiliate.db"
    webhook_url: Optional[str] = None
    webhook_secret_token: Optional[str] = None
    host: str = "0.0.0.0"
    port: int = 8080

    @validator("bot_token", "database_url", pre=True)
    def _not_blank(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("must not be empty")
        return value

    @validator("target_chat_id", pre=True)
    def _target_chat_id(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("must not be empty")
        numeric = int(value)
        if numeric == 0:
            raise ValueError("must not be zero")
        return numeric

    @validator("webhook_url", "webhook_secret_token", "host", pre=True)
    def _normalize_optional(cls, value: Any) -> Any:
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                return None
            return trimmed
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
