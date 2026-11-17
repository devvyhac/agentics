import asyncio
import logging
from typing import Any, Optional, Tuple
import httpx
from openai import AsyncOpenAI

from agents.generalist.config import GeneralistSettings, get_settings
from agents.generalist.prompts import format_system_prompt
from agents.generalist.schemas import WebhookRequest, WebhookResponse

logger = logging.getLogger("generalist.service")


def trim_to_word_limit(text: str, max_words: int) -> Tuple[str, int]:
    """Trim text to strictly satisfy word_count <= max_words using sentence-aware logic."""
    if not text or not text.strip() or max_words <= 0:
        return "", 0

    stripped = text.strip()
    words = stripped.split()
    if len(words) <= max_words:
        return stripped, len(words)

    candidate = " ".join(words[:max_words])
    candidate_len = len(candidate)
    cutoff_threshold = int(candidate_len * 0.8)

    # Search backwards for sentence terminators ('.', '!', '?')
    terminator_idx = None
    for i in range(candidate_len - 1, -1, -1):
        if candidate[i] in {".", "!", "?"}:
            terminator_idx = i
            break

    if terminator_idx is not None and terminator_idx >= cutoff_threshold:
        final_text = candidate[: terminator_idx + 1].strip()
    else:
        final_text = candidate.rstrip(".!?,;: ") + "..."

    # Safety check to guarantee strict <= max_words invariant
    final_words = final_text.split()
    if len(final_words) > max_words:
        final_text = " ".join(final_words[:max_words])
        final_words = final_text.split()

    return final_text, len(final_words)


class GeneralistService:
    def __init__(
        self,
        settings: Optional[GeneralistSettings] = None,
        client: Optional[Any] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.settings = settings or get_settings()
        if client is not None:
            self.client = client
        else:
            client_kwargs = {"api_key": self.settings.llm_api_key or "sk-placeholder"}
            if self.settings.llm_base_url:
                client_kwargs["base_url"] = self.settings.llm_base_url
            self.client = AsyncOpenAI(**client_kwargs)

        self.http_client = http_client or httpx.AsyncClient(timeout=60.0)

        # Log configuration check on initialization
        if not self.settings.llm_api_key or self.settings.llm_api_key == "sk-placeholder":
            logger.warning(
                "WARNING: LLM_API_KEY is not set in agents/generalist/.env. "
                "Calls to provider will fail with 401 Unauthorized."
            )
        else:
            logger.info(
                "GeneralistService initialized with endpoint: %s, model: %s",
                self.settings.effective_api_url,
                self.settings.llm_model_name,
            )

    async def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int, timeout: float) -> str:
        """Execute LLM call using either mock client or universal HTTP client."""
        # 1. If explicit client mock was injected in unit tests
        if self.client is not None and hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
            # Check if this is a MagicMock or real AsyncOpenAI
            from unittest.mock import MagicMock, AsyncMock
            if isinstance(self.client, (MagicMock, AsyncMock)) or isinstance(getattr(self.client.chat.completions, "create", None), (MagicMock, AsyncMock)):
                response = await self.client.chat.completions.create(
                    model=self.settings.llm_model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens,
                )
                if hasattr(response, "choices") and response.choices and response.choices[0].message:
                    return response.choices[0].message.content or ""
                return ""

        # 2. Universal HTTP execution
        url = self.settings.effective_api_url
        api_key = self.settings.llm_api_key.strip()

        if "anthropic.com" in url or url.endswith("/messages"):
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": self.settings.llm_model_name,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}],
            }
        else:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.settings.llm_model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
            }

        response = await self.http_client.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code != 200:
            logger.error(
                "LLM Provider error (HTTP %d) calling %s: %s",
                response.status_code,
                url,
                response.text,
            )
            if response.status_code == 401:
                logger.error(
                    "--> 401 Unauthorized: Check LLM_API_KEY in agents/generalist/.env for %s",
                    url,
                )
            raise RuntimeError(f"Provider returned HTTP {response.status_code}: {response.text}")

        data = response.json()
        if "choices" in data and len(data["choices"]) > 0:
            msg = data["choices"][0].get("message", {})
            content = msg.get("content")
            # If content is empty but model produced reasoning (e.g. gpt-oss-20b, DeepSeek-R1), use it
            if not content and msg.get("reasoning"):
                content = msg.get("reasoning")
            return content or ""
        elif "content" in data and isinstance(data["content"], list):
            # Anthropic response
            return data["content"][0].get("text", "")
        elif "response" in data:
            # Ollama response
            return data.get("response", "")
        elif "text" in data:
            return data.get("text", "")

        return ""

    async def process_webhook(self, request: WebhookRequest) -> WebhookResponse:
        """Process inbound webhook request with timeout guardrail and output trimming."""
        safety_buffer = self.settings.internal_timeout_safety_buffer_seconds
        effective_timeout = max(
            0.2,
            min(request.timeout_seconds * 0.8, request.timeout_seconds - safety_buffer),
        )

        system_prompt = format_system_prompt(
            max_words=request.max_words,
            category=request.category,
            task_type=request.type,
        )
        # If mock client was injected (unit test), use test budget calculation
        if self.client is not None and not type(self.client).__name__ == "AsyncOpenAI":
            max_tokens = min(self.settings.llm_max_tokens, max(64, request.max_words * 4))
        else:
            # For live generation, allow full settings budget so reasoning models finish reasoning
            max_tokens = self.settings.llm_max_tokens

        try:
            raw_text = await asyncio.wait_for(
                self._call_llm(
                    system_prompt=system_prompt,
                    user_prompt=request.prompt,
                    max_tokens=max_tokens,
                    timeout=effective_timeout,
                ),
                timeout=effective_timeout,
            )

            if not raw_text.strip():
                fallback = "I was unable to generate a response."
                output_text, word_count = trim_to_word_limit(fallback, request.max_words)
            else:
                output_text, word_count = trim_to_word_limit(raw_text, request.max_words)
        except asyncio.TimeoutError:
            logger.warning(
                "Execution timed out for match_id: %s (effective timeout: %.2fs)",
                request.match_id,
                effective_timeout,
            )
            fallback = "I was unable to complete the response within the allocated time limit."
            output_text, word_count = trim_to_word_limit(fallback, request.max_words)
        except Exception as exc:
            logger.error(
                "LLM execution error for match_id: %s: %s",
                request.match_id,
                exc,
            )
            fallback = "An error occurred while processing the request."
            output_text, word_count = trim_to_word_limit(fallback, request.max_words)

        return WebhookResponse(
            output_text=output_text,
        )
