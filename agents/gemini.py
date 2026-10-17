"""Shared Gemini plumbing: client setup and one structured-output call with a real deadline.

Uses the Gemini Interactions API (google-genai >= 2.3) through the async client, so `timeout`
is a real wall-clock deadline (asyncio.wait_for cancels the request); the SDK's own `timeout`
is only a per-read socket timeout. The SDK's built-in retries are off; callers choose how many
attempts they want (normally 2: first try + one retry).

Two ways in: Vertex AI (GOOGLE_GENAI_USE_VERTEXAI=true, production: the Cloud Run service
account's credentials, no API key) or the Gemini API with GEMINI_API_KEY (local development).
On Vertex AI the Interactions API is served from the "global" location only (preview).

Every attempt writes one "gemini_call" log line with a running count, the label, model,
outcome, time and token counts. No prompt text, photo, or customer data is ever logged.
"""

import asyncio
import itertools
import logging
import threading
import time
from typing import Any, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from backend.api.config import Settings

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


class GeminiNotConfigured(RuntimeError):
    """The settings Gemini needs are missing. str(exc) names the missing setting."""


def make_client(settings: Settings) -> genai.Client:
    # The SDK retries up to 3x by default; we do our own retries.
    http_options = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
    if settings.google_genai_use_vertexai:
        if not settings.gcp_project_id.strip():
            raise GeminiNotConfigured("GCP_PROJECT_ID is missing.")
        # Application Default Credentials: on Cloud Run, the service account (needs
        # roles/aiplatform.user). No API key.
        return genai.Client(vertexai=True, project=settings.gcp_project_id.strip(),
                            location=settings.gemini_location.strip() or "global",
                            http_options=http_options)
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value():
        raise GeminiNotConfigured("GEMINI_API_KEY is missing.")
    return genai.Client(api_key=settings.gemini_api_key.get_secret_value(),
                        http_options=http_options)


# Gemini usage, for honest reporting: one count per attempt (a retry is a second call), per
# process. Totals over time come from the logs (infra/DEPLOY.md shows the query).
_call_numbers = itertools.count(1)
_count_lock = threading.Lock()


def _next_call_number() -> int:
    with _count_lock:
        return next(_call_numbers)


def _log_call(n: int, label: str, model: str, attempt: int, ok: bool, seconds: float,
              usage=None, error: Exception | None = None) -> None:
    """One line, no prompt text or customer data: only counts, names and timings."""
    fields = {
        "n": n, "label": label.replace(" ", "_"), "model": model, "attempt": attempt,
        "ok": ok, "seconds": f"{seconds:.1f}",
        "in_tokens": getattr(usage, "total_input_tokens", None),
        "out_tokens": getattr(usage, "total_output_tokens", None),
    }
    if error is not None:
        fields["error"] = type(error).__name__
        status = getattr(error, "status_code", None)
        if isinstance(status, int):
            fields["status"] = status
    text = " ".join(f"{k}={'-' if v is None else v}" for k, v in fields.items())
    (log.info if ok else log.warning)("gemini_call %s", text)


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
        n = _next_call_number()
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
                    store=False,  # don't keep menu photos or order text on Google's side
                    timeout=timeout,
                ),
                timeout=timeout,
            )
            usage = getattr(interaction, "usage", None)
            result = schema.model_validate_json(interaction.output_text or "")
            _log_call(n, label, model, attempt, True, time.monotonic() - started, usage)
            return result
        except Exception as exc:  # timeouts, HTTP errors, no response, bad JSON
            last = exc
            # Only the error type and HTTP status: an error message can quote the input.
            _log_call(n, label, model, attempt, False, time.monotonic() - started, error=exc)
            if not is_retryable(exc):
                break
    assert last is not None
    raise last
