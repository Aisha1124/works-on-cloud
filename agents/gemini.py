"""Shared Gemini plumbing: client setup and one structured-output call with a real deadline.

Uses the Gemini Interactions API (google-genai >= 2.3) through the async client, so `timeout`
is a real wall-clock deadline (asyncio.wait_for cancels the request); the SDK's own `timeout`
is only a per-read socket timeout. The SDK's built-in retries are off; callers choose how many
attempts they want (normally 2: first try + one retry).
"""

import asyncio
import logging
import time
from typing import Any, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from backend.api.config import Settings

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


class GeminiNotConfigured(RuntimeError):
    """GEMINI_API_KEY or GEMINI_MODEL is missing."""


def make_client(settings: Settings) -> genai.Client:
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value():
        raise GeminiNotConfigured("GEMINI_API_KEY is missing.")
    # The SDK retries up to 3x by default; we do our own retries.
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
    )


def is_retryable(exc: Exception) -> bool:
    """Retry timeouts, network errors, 408/429/5xx and invalid JSON. Not other 4xx."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500:
        return status in (408, 429)
    return True


async def call_structured(
    client,
    *,
    model: str,
    system_instruction: str,
    input: list[dict[str, Any]],
    schema: type[M],
    timeout: float,
    attempts: int = 2,
    thinking_level: str = "low",
    label: str = "gemini",
) -> M:
    """One structured-output call, retried on retryable errors. Raises the last error."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            interaction = await asyncio.wait_for(
                client.aio.interactions.create(
                    model=model,
                    system_instruction=system_instruction,
                    input=input,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema.model_json_schema(),
                    },
                    generation_config={"thinking_level": thinking_level, "temperature": 0},
                    timeout=timeout,
                ),
                timeout=timeout,
            )
            result = schema.model_validate_json(interaction.output_text or "")
            usage = getattr(interaction, "usage", None)
            log.info(
                "%s ok in %.1fs (attempt %d, %s output tokens)",
                label, time.monotonic() - started, attempt,
                getattr(usage, "total_output_tokens", "?"),
            )
            return result
        except Exception as exc:  # timeouts, HTTP errors, no response, bad JSON
            last = exc
            log.warning(
                "%s attempt %d failed after %.1fs: %s: %s",
                label, attempt, time.monotonic() - started, type(exc).__name__, str(exc)[:300],
            )
            if not is_retryable(exc):
                break
    assert last is not None
    raise last
