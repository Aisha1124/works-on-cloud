"""Catalog agent: menu photo(s) -> CatalogDraft, using Gemini vision with structured output.

Uses the Gemini Interactions API (google-genai >= 2.3) through the async client, so the
45 s limit is a real wall-clock deadline (asyncio.wait_for cancels the request); the SDK's
own `timeout` is only a per-read socket timeout. Photos are read in parallel, one call per
photo, so one bad photo becomes a warning instead of losing the whole upload. Results are
merged and deduped in Python (normalize.py).
"""

import asyncio
import base64
import logging
import time

from google import genai
from google.genai import types

from agents.catalog.images import preprocess
from agents.catalog.normalize import merge_drafts, to_draft
from agents.catalog.prompt import SYSTEM_PROMPT, USER_PROMPT
from agents.catalog.schema import CatalogDraft, GeminiCatalog
from backend.api.config import Settings, get_settings

log = logging.getLogger(__name__)

TIMEOUT_S = 45
ATTEMPTS = 2  # first try + one retry
IMAGE_RESOLUTION = "high"
THINKING_LEVEL = "low"  # "minimal" is rejected by gemini-3.8-flash

FRIENDLY_ERROR = (
    "We couldn't read this menu photo right now. Please try again, or use a clearer, "
    "straight-on photo with good light."
)
BUSY_ERROR = "Photo reading is busy right now. Please try again in a few minutes."
SLOW_ERROR = (
    "This menu took too long to read. Please try again, or upload it as two photos "
    "(top half and bottom half)."
)


def _friendly_message(exc: Exception | None) -> str:
    if getattr(exc, "status_code", None) == 429 or (
        isinstance(getattr(exc, "status_code", None), int) and exc.status_code >= 500
    ):
        return BUSY_ERROR
    if isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__:
        return SLOW_ERROR
    return FRIENDLY_ERROR


class CatalogExtractionError(RuntimeError):
    """Extraction failed. str(exc) is safe to show the owner."""

    def __init__(self, message: str = FRIENDLY_ERROR):
        super().__init__(message)


def make_client(settings: Settings) -> genai.Client:
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value():
        raise CatalogExtractionError("Photo reading is not set up yet (GEMINI_API_KEY is missing).")
    # The SDK retries up to 3x by default; we do exactly one retry ourselves.
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
    )


def _is_retryable(exc: Exception) -> bool:
    """Retry timeouts, network errors, 408/429/5xx and invalid JSON. Not other 4xx."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500:
        return status in (408, 429)
    return True


async def _call_gemini(client, model: str, jpeg: bytes) -> GeminiCatalog:
    last: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        started = time.monotonic()
        try:
            interaction = await asyncio.wait_for(
                client.aio.interactions.create(
                    model=model,
                    system_instruction=SYSTEM_PROMPT,
                    input=[
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image",
                            "data": base64.b64encode(jpeg).decode("ascii"),
                            "mime_type": "image/jpeg",
                            "resolution": IMAGE_RESOLUTION,
                        },
                    ],
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": GeminiCatalog.model_json_schema(),
                    },
                    generation_config={"thinking_level": THINKING_LEVEL, "temperature": 0},
                    timeout=TIMEOUT_S,
                ),
                timeout=TIMEOUT_S,
            )
            result = GeminiCatalog.model_validate_json(interaction.output_text or "")
            usage = getattr(interaction, "usage", None)
            log.info(
                "catalog extraction ok in %.1fs (attempt %d, %s output tokens)",
                time.monotonic() - started, attempt, getattr(usage, "total_output_tokens", "?"),
            )
            return result
        except Exception as exc:  # timeouts, HTTP errors, no response, bad JSON
            last = exc
            log.warning(
                "catalog extraction attempt %d failed after %.1fs: %s: %s",
                attempt, time.monotonic() - started, type(exc).__name__, str(exc)[:300],
            )
            if not _is_retryable(exc):
                break
    raise CatalogExtractionError(_friendly_message(last)) from last


async def extract_catalog_async(
    images: list[bytes], *, client=None, settings: Settings | None = None
) -> CatalogDraft:
    """Read 1+ menu photos into one merged CatalogDraft.

    Raises ImageError (bad file, friendly message) or CatalogExtractionError (every photo
    failed, friendly message). If only some photos fail, the result carries a warning.
    """
    if not images:
        raise ValueError("No photos given.")
    settings = settings or get_settings()
    if not settings.gemini_model:
        raise CatalogExtractionError("Photo reading is not set up yet (GEMINI_MODEL is missing).")
    # Pillow work is CPU-bound; keep it off the event loop. Raises ImageError before any API call.
    jpegs = await asyncio.gather(*(asyncio.to_thread(preprocess, data) for data in images))
    client = client or make_client(settings)

    results = await asyncio.gather(
        *(_call_gemini(client, settings.gemini_model, jpeg) for jpeg in jpegs),
        return_exceptions=True,
    )
    drafts: list[CatalogDraft] = []
    failed: list[int] = []
    errors: list[CatalogExtractionError] = []
    for i, result in enumerate(results, start=1):
        if isinstance(result, CatalogExtractionError):
            failed.append(i)
            errors.append(result)
        elif isinstance(result, BaseException):
            raise result
        else:
            drafts.append(to_draft(result))

    if not drafts:
        raise errors[0]
    merged = merge_drafts(drafts)
    if failed:
        nums = ", ".join(str(n) for n in failed)
        merged.warnings.insert(
            0, f"We couldn't read photo {nums} of {len(jpegs)}. Try uploading it again."
        )
    return merged


def extract_catalog(
    images: list[bytes], *, client=None, settings: Settings | None = None
) -> CatalogDraft:
    """Sync wrapper for scripts and tests. Don't call from inside a running event loop."""
    return asyncio.run(extract_catalog_async(images, client=client, settings=settings))
