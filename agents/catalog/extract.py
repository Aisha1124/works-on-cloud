"""Catalog agent: menu photo(s) -> CatalogDraft, using Gemini vision with structured output.

The Gemini call itself (Interactions API, wall-clock deadline, one retry) lives in
agents/gemini.py. Photos are read in parallel, one call per photo, so one bad photo becomes a
warning instead of losing the whole upload. Results are merged and deduped in Python
(normalize.py).
"""

import asyncio
import base64

from agents import gemini
from agents.catalog.images import preprocess
from agents.catalog.normalize import merge_drafts, to_draft
from agents.catalog.prompt import SYSTEM_PROMPT, USER_PROMPT
from agents.catalog.schema import CatalogDraft, GeminiCatalog
from backend.api.config import Settings, get_settings

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


def make_client(settings: Settings):
    try:
        return gemini.make_client(settings)
    except gemini.GeminiNotConfigured as exc:
        raise CatalogExtractionError(
            "Photo reading is not set up yet (GEMINI_API_KEY is missing)."
        ) from exc


async def _call_gemini(client, model: str, jpeg: bytes) -> GeminiCatalog:
    try:
        return await gemini.call_structured(
            client,
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
            schema=GeminiCatalog,
            timeout=TIMEOUT_S,
            attempts=ATTEMPTS,
            thinking_level=THINKING_LEVEL,
            label="catalog extraction",
        )
    except Exception as exc:
        raise CatalogExtractionError(_friendly_message(exc)) from exc


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
