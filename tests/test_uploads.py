"""Upload abuse and cost limits: real file type from the bytes, 10 MB per photo, EXIF (GPS)
stripped before storing or sending to Gemini, Gemini usage logged without personal data, and
the Vertex AI / API key client choice."""

import asyncio
import base64
import io
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import BaseModel

from agents import gemini
from agents.catalog import extract as ex
from agents.catalog.images import NOT_AN_IMAGE, preprocess, sniff_image_type
from agents.gemini import make_client as real_make_client  # before conftest replaces it
from backend.api.config import Settings
from backend.api.main import create_app
from tests import gemini_fake

GPS_IFD = 0x8825
READING = {"shop_name_guess": "", "sections": [{"category": "Kuih", "items": [
    {"name": "Kuih Lapis", "price": "$16", "unit": "20 pcs", "confidence": 0.95}]}]}


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    return create_app(Settings(_env_file=None, data_dir=tmp_path / "data",
                               uploads_dir=tmp_path / "uploads", dashboard_dist=dist_dir,
                               gemini_model="test-model"))


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def fake_gemini(monkeypatch):
    fake = gemini_fake.fake_client(*[json.dumps(READING)] * 5)
    monkeypatch.setattr(ex, "make_client", lambda settings: fake)
    return fake


def image_bytes(fmt: str, size=(60, 40), **save) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 150, 90)).save(buf, fmt, **save)
    return buf.getvalue()


def jpeg_with_gps() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif.get_ifd(GPS_IFD).update({1: "N", 2: (1.0, 21.0, 10.0), 3: "E", 4: (103.0, 56.0, 30.0)})
    data = image_bytes("JPEG", exif=exif.tobytes())
    with Image.open(io.BytesIO(data)) as img:  # sanity: the GPS location really is in there
        assert img.getexif().get_ifd(GPS_IFD)
    return data


def has_exif(data: bytes) -> bool:
    with Image.open(io.BytesIO(data)) as img:
        return bool(img.getexif()) or "exif" in img.info or b"Exif\x00\x00" in data


# --- file type from the bytes ------------------------------------------------------------


def test_sniff_image_type():
    assert sniff_image_type(image_bytes("JPEG")) == "jpeg"
    assert sniff_image_type(image_bytes("PNG")) == "png"
    assert sniff_image_type(image_bytes("WEBP")) == "webp"
    assert sniff_image_type(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20) == "heic"
    assert sniff_image_type(image_bytes("GIF")) is None
    assert sniff_image_type(b"%PDF-1.7 ...") is None
    assert sniff_image_type(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert sniff_image_type(b"") is None


def test_text_file_named_jpg_is_rejected_before_gemini(api, fake_gemini):
    r = api.post("/api/shops/draft",
                 files=[("images", ("menu.jpg", b"just some text", "image/jpeg"))])
    assert r.status_code == 400
    assert r.json() == {"detail": NOT_AN_IMAGE}
    assert fake_gemini.aio.interactions.calls == []


def test_png_named_txt_is_accepted(api, fake_gemini):
    r = api.post("/api/shops/draft",
                 files=[("images", ("menu.txt", image_bytes("PNG"), "text/plain"))])
    assert r.status_code == 200, r.text


def test_photos_over_10_mb_are_rejected(api, fake_gemini):
    big = image_bytes("PNG") + b"\x00" * (10 * 1024 * 1024)
    r = api.post("/api/shops/draft", files=[("images", ("menu.png", big, "image/png"))])
    assert r.status_code == 400
    assert r.json()["detail"] == "Each photo must be 10 MB or smaller."
    assert fake_gemini.aio.interactions.calls == []


def test_rejected_uploads_do_not_use_up_the_rate_limit(api, fake_gemini):
    for _ in range(6):
        api.post("/api/shops/draft", files=[("images", ("x.jpg", b"nope", "image/jpeg"))])
    r = api.post("/api/shops/draft", files=[("images", ("menu.jpg", image_bytes("JPEG"),
                                                          "image/jpeg"))])
    assert r.status_code == 200


# --- EXIF / GPS is stripped -----------------------------------------------------------------


def test_preprocess_drops_exif_and_gps():
    cleaned = preprocess(jpeg_with_gps())
    assert not has_exif(cleaned)


def test_stored_photo_and_gemini_photo_have_no_gps(api, tmp_path, fake_gemini):
    r = api.post("/api/shops/draft",
                 files=[("images", ("IMG_0001.jpg", jpeg_with_gps(), "image/jpeg"))])
    assert r.status_code == 200, r.text
    shop_id = r.json()["shop"]["id"]
    (stored,) = (tmp_path / "uploads" / shop_id).iterdir()
    assert stored.suffix == ".jpg"
    assert not has_exif(stored.read_bytes())
    (call,) = fake_gemini.aio.interactions.calls
    (image,) = [part for part in call["input"] if part["type"] == "image"]
    sent = base64.b64decode(image["data"])
    assert sent == stored.read_bytes()  # what Gemini saw is what was stored
    assert not has_exif(sent)


# --- Gemini usage log -------------------------------------------------------------------------


class Out(BaseModel):
    ok: bool


def call(client, prompt="SECRET MENU TEXT from customer +65 9123 4567"):
    return asyncio.run(gemini.call_structured(
        client, model="test-model", system_instruction="system", schema=Out, timeout=5,
        input=[{"type": "text", "text": prompt}], label="catalog extraction"))


def test_every_gemini_call_is_logged_without_personal_data(caplog):
    with caplog.at_level(logging.INFO, logger="agents.gemini"):
        call(gemini_fake.fake_client('{"ok": true}'))
        with pytest.raises(gemini_fake.FakeStatusError):
            call(gemini_fake.fake_client(gemini_fake.FakeStatusError(400)))
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("gemini_call ")]
    assert len(lines) == 2
    ok, failed = lines
    assert "label=catalog_extraction model=test-model attempt=1 ok=True" in ok
    assert "ok=False" in failed and "error=FakeStatusError status=400" in failed
    first, second = (int(line.split("n=")[1].split()[0]) for line in lines)
    assert second == first + 1  # a running count
    assert "SECRET" not in caplog.text and "9123" not in caplog.text


def test_retries_count_as_calls(caplog):
    with caplog.at_level(logging.INFO, logger="agents.gemini"):
        call(gemini_fake.fake_client(gemini_fake.FakeStatusError(503), '{"ok": true}'))
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("gemini_call ")]
    assert ["attempt=1" in lines[0], "attempt=2" in lines[1]] == [True, True]


def test_interactions_are_not_stored():
    client = gemini_fake.fake_client('{"ok": true}')
    call(client)
    assert client.aio.interactions.calls[0]["store"] is False


# --- Vertex AI in production, API key locally ----------------------------------------------


@pytest.fixture
def client_kwargs(monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini.genai, "Client", lambda **kw: seen.update(kw) or "client")
    return seen


def test_vertex_ai_uses_the_project_and_no_api_key(client_kwargs):
    settings = Settings(_env_file=None, google_genai_use_vertexai=True, gcp_project_id="kc-prod",
                        gemini_api_key="should-not-be-used")
    assert real_make_client(settings) == "client"
    assert client_kwargs["vertexai"] is True
    assert (client_kwargs["project"], client_kwargs["location"]) == ("kc-prod", "global")
    assert "api_key" not in client_kwargs


def test_vertex_ai_needs_a_project(client_kwargs):
    with pytest.raises(gemini.GeminiNotConfigured, match="GCP_PROJECT_ID"):
        real_make_client(Settings(_env_file=None, google_genai_use_vertexai=True))


def test_local_development_uses_the_api_key(client_kwargs):
    real_make_client(Settings(_env_file=None, gemini_api_key="AIza-test"))
    assert client_kwargs["api_key"] == "AIza-test"
    assert "vertexai" not in client_kwargs
    with pytest.raises(gemini.GeminiNotConfigured, match="GEMINI_API_KEY"):
        real_make_client(Settings(_env_file=None))


def test_vertex_flag_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GEMINI_LOCATION", "global")
    settings = Settings(_env_file=None)
    assert settings.google_genai_use_vertexai is True and settings.gemini_location == "global"
