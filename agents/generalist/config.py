from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

_CURRENT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _CURRENT_DIR.parent.parent


class GeneralistSettings(BaseSettings):
    llm_base_url: Optional[str] = None
    llm_api_url: Optional[str] = None
    llm_api_key: str = ""
    llm_model_name: str = "gpt-4o-mini"
    model_tag: str = "generalist-v1"
    llm_max_tokens: int = 4096
    internal_timeout_safety_buffer_seconds: float = 2.0
    webhook_secret: Optional[str] = None
    port: int = 8001
    agent_host: str = "0.0.0.0"

    model_config = SettingsConfigDict(
        env_file=(
            _ROOT_DIR / ".env",
            _CURRENT_DIR / ".env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def effective_api_url(self) -> str:
        """Resolve full API endpoint URL from llm_api_url or llm_base_url."""
        url = (self.llm_api_url or self.llm_base_url or "").strip()
        if not url:
            return "https://api.openai.com/v1/chat/completions"
        if url.endswith("/chat/completions") or url.endswith("/messages") or url.endswith("/generate"):
            return url
        return url.rstrip("/") + "/chat/completions"


@lru_cache
def get_settings() -> GeneralistSettings:
    return GeneralistSettings()
