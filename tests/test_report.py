"""Report this shop: emailed to ADMIN_EMAIL, logged in the platform audit log, rate-limited."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.config import Settings
from backend.api.main import create_app
from backend.external import PLATFORM
from backend.models import Shop


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    return create_app(Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir,
                               base_url="https://kc.example.sg", admin_email="admin@kc.example"))


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def shop(app) -> Shop:
    return app.state.store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", published=True,
                                          owner_email="owner@example.sg"))


def report(api, slug="mak-kuih", **kw):
    return api.post(f"/api/public/shops/{slug}/report",
                    json={"reason": "wrong_info", "details": "Prices are <b>old</b>", **kw})


def test_report_emails_the_admin_and_is_logged_privately(api, app, shop, mail):
    r = report(api, email="Reporter@Example.SG")
    assert r.status_code == 200 and r.json()["message"] == "Thank you. We'll look into it."
    (email,) = mail.sent
    assert email.to == "admin@kc.example"
    assert email.subject == "Shop reported: Mak's Kuih (Wrong prices or menu)"
    assert "reporter@example.sg" in email.text and "https://kc.example.sg/s/mak-kuih" in email.text
    assert "&lt;b&gt;old&lt;/b&gt;" in email.html and "<b>old</b>" not in email.html
    store = app.state.store
    assert [e.action for e in store.list_audit_events(shop.id)] == []  # the owner never sees it
    (event,) = [e for e in store.list_audit_events(PLATFORM) if e.action == "shop_reported"]
    assert event.entity_id == shop.id and event.details["reporter_email"] == "r***@example.sg"
    assert "Reporter@" not in str(event.details)


def test_report_needs_a_known_reason_and_a_real_email(api, shop):
    assert api.post("/api/public/shops/mak-kuih/report", json={"reason": "spam"}).status_code == 422
    assert report(api, details="x" * 1001).status_code == 422
    r = report(api, email="nope")
    assert r.status_code == 400 and "email" in r.json()["detail"]
    assert report(api, slug="nope").status_code == 404


def test_reports_are_rate_limited(api, shop):
    assert [report(api).status_code for _ in range(4)] == [200, 200, 200, 429]


def test_without_admin_email_the_report_is_still_logged(tmp_path, dist_dir, mail):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir))
    app.state.store.save_shop(Shop(slug="mak-kuih", name="Mak's Kuih", published=True))
    assert report(TestClient(app)).status_code == 200
    assert mail.sent == []
    event = app.state.store.list_audit_events(PLATFORM)[0]
    assert event.action == "shop_reported" and event.details["emailed_admin"] is False
