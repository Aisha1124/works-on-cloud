import base64
import io
import json
import time

import httpx
import pytest
from PIL import Image

from agents.catalog import extract as ex
from agents.catalog.images import MAX_SIDE, ImageError, preprocess
from backend.api.config import Settings
from tests import gemini_fake
from tests.gemini_fake import FakeStatusError

GOOD = {
    "shop_name_guess": "Ah Ma Kueh",
    "sections": [
        {
            "category": "Kuih",
            "items": [
                {
                    "name": "Kuih Lapis", "confidence": 0.95,
                    "variants": [
                        {"label": "50 pcs", "price": "$40"},
                        {"label": "20 pcs", "price": "$16"},
                    ],
                },
            ],
        },
    ],
}


def jpeg(w=100, h=50) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


def fake_client(*script):
    return gemini_fake.fake_client(*script, hang_result=json.dumps(GOOD))


@pytest.fixture
def settings():
    return Settings(_env_file=None, gemini_model="test-model", gemini_api_key="k")


# --- preprocess ---------------------------------------------------------------------


def test_preprocess_resizes_long_side_and_outputs_jpeg():
    buf = io.BytesIO()
    Image.new("RGBA", (4000, 1000), (0, 0, 0, 0)).save(buf, "PNG")
    out = Image.open(io.BytesIO(preprocess(buf.getvalue())))
    assert out.format == "JPEG"
    assert out.size == (MAX_SIDE, 512)
    assert out.getpixel((10, 10)) == (255, 255, 255)  # transparency flattened to white


def test_preprocess_applies_exif_rotation():
    img = Image.new("RGB", (300, 100), (0, 0, 255))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    out = Image.open(io.BytesIO(preprocess(buf.getvalue())))
    assert out.size == (100, 300)


def test_preprocess_converts_webp():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "WEBP")
    assert Image.open(io.BytesIO(preprocess(buf.getvalue()))).format == "JPEG"


def test_preprocess_rejects_non_image():
    with pytest.raises(ImageError, match="doesn't look like a photo"):
        preprocess(b"%PDF-1.4 not an image")


# --- extract_catalog ------------------------------------------------------------------


def test_extract_happy_path(settings):
    client = fake_client(json.dumps(GOOD))
    draft = ex.extract_catalog([jpeg()], client=client, settings=settings)

    assert draft.shop_name_guess == "Ah Ma Kueh"
    [p] = draft.products
    assert [v.label for v in p.variants] == ["20 pcs", "50 pcs"]
    assert p.base_price is None

    call = client.aio.interactions.calls[0]
    assert call["model"] == "test-model"
    assert call["timeout"] == ex.TIMEOUT_S
    assert call["response_format"]["mime_type"] == "application/json"
    image = call["input"][1]
    assert image["type"] == "image" and image["mime_type"] == "image/jpeg"
    assert Image.open(io.BytesIO(base64.b64decode(image["data"]))).format == "JPEG"


def test_extract_retries_once_after_timeout(settings):
    client = fake_client(httpx.ReadTimeout("slow"), json.dumps(GOOD))
    draft = ex.extract_catalog([jpeg()], client=client, settings=settings)
    assert len(draft.products) == 1
    assert len(client.aio.interactions.calls) == 2


def test_extract_retries_once_after_bad_json(settings):
    client = fake_client("{not json", json.dumps(GOOD))
    assert len(ex.extract_catalog([jpeg()], client=client, settings=settings).products) == 1


def test_extract_gives_friendly_error_after_two_failures(settings):
    client = fake_client(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow again"))
    with pytest.raises(ex.CatalogExtractionError) as info:
        ex.extract_catalog([jpeg()], client=client, settings=settings)
    assert str(info.value) == ex.SLOW_ERROR
    assert "Traceback" not in str(info.value)
    assert len(client.aio.interactions.calls) == 2


def test_extract_one_bad_photo_becomes_warning(settings):
    second = {"shop_name_guess": "", "sections": [
        {"category": "", "items": [{"name": "Ondeh Ondeh", "price": "$5", "confidence": 0.9}]}]}
    client = fake_client(RuntimeError("boom"), RuntimeError("boom"), json.dumps(second))
    draft = ex.extract_catalog([jpeg(), jpeg()], client=client, settings=settings)
    assert [p.name for p in draft.products] == ["Ondeh Ondeh"]
    assert draft.warnings[0].startswith("We couldn't read photo 1 of 2")


def test_extract_merges_and_dedupes_photos(settings):
    client = fake_client(json.dumps(GOOD), json.dumps(GOOD))
    draft = ex.extract_catalog([jpeg(), jpeg()], client=client, settings=settings)
    assert len(draft.products) == 1


def test_extract_rejects_bad_image_before_calling_gemini(settings):
    client = fake_client()
    with pytest.raises(ImageError):
        ex.extract_catalog([b"nope"], client=client, settings=settings)
    assert client.aio.interactions.calls == []


def test_extract_needs_model_name():
    with pytest.raises(ex.CatalogExtractionError, match="GEMINI_MODEL"):
        ex.extract_catalog([jpeg()], client=fake_client(),
                           settings=Settings(_env_file=None, gemini_model=""))


def test_extract_enforces_wall_clock_deadline(settings, monkeypatch):
    monkeypatch.setattr(ex, "TIMEOUT_S", 0.05)
    client = fake_client(5, json.dumps(GOOD))  # first call hangs, the retry answers
    started = time.monotonic()
    draft = ex.extract_catalog([jpeg()], client=client, settings=settings)
    assert time.monotonic() - started < 2
    assert len(draft.products) == 1
    assert len(client.aio.interactions.calls) == 2


def test_extract_does_not_retry_bad_request(settings):
    client = fake_client(FakeStatusError(400), json.dumps(GOOD))
    with pytest.raises(ex.CatalogExtractionError):
        ex.extract_catalog([jpeg()], client=client, settings=settings)
    assert len(client.aio.interactions.calls) == 1


def test_extract_retries_rate_limit(settings):
    client = fake_client(FakeStatusError(429), json.dumps(GOOD))
    assert len(ex.extract_catalog([jpeg()], client=client, settings=settings).products) == 1


def test_extract_rate_limit_twice_says_busy(settings):
    client = fake_client(FakeStatusError(429), FakeStatusError(429))
    with pytest.raises(ex.CatalogExtractionError) as info:
        ex.extract_catalog([jpeg()], client=client, settings=settings)
    assert str(info.value) == ex.BUSY_ERROR


def test_extract_bad_json_twice_gives_generic_message(settings):
    client = fake_client("{bad", "{bad")
    with pytest.raises(ex.CatalogExtractionError) as info:
        ex.extract_catalog([jpeg()], client=client, settings=settings)
    assert str(info.value) == ex.FRIENDLY_ERROR
