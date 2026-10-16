"""Owner accounts by email: go live with an email, confirm it, sign in by one-time link, session
cookies, and order emails. Email goes to a fake mailer (tests/conftest.py); nothing is sent."""

import asyncio
import json
import logging
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.commerce import service as commerce
from backend import mailer, owner_session
from backend.api.config import Settings
from backend.api.main import create_app
from backend.models import Channel, Product, Shop, Variant, utc_now
from backend.timeutil import now_sg
from tests.conftest import give_key

KEY = "kc_draft-key"
CSRF = {"X-Requested-With": "kampungcart"}


@pytest.fixture
def app(tmp_path: Path, dist_dir: Path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir,
                        base_url="https://kc.example.sg", gemini_model="")
    return create_app(settings)


@pytest.fixture
def api(app) -> TestClient:
    return TestClient(app, base_url="https://kc.example.sg")


@pytest.fixture
def store(app):
    return app.state.store


def draft(store, slug="auntie-lim-ab12", key=KEY) -> Shop:
    shop = store.save_shop(Shop(slug=slug, name="Auntie Lim"))
    store.save_product(Product(shop_id=shop.id, name="Pandan Chiffon", base_price=Decimal("18")))
    return give_key(store, shop, key)


def go_live(api, shop, email="Siti.Bakes@Example.SG", name="Auntie Lim's Bakes", key=KEY):
    return api.post(f"/api/shops/{shop.id}/publish", headers={"X-Owner-Key": key},
                    json={"name": name, "email": email})


def token_in(email, page) -> str:
    return re.search(rf"/{page}\?token=([\w-]+)", email.text).group(1)


def live_shop(store, email="owner@example.sg", slug="mak-kuih") -> Shop:
    shop = store.save_shop(Shop(slug=slug, name="Mak's Kuih", published=True, hours="Daily 8am-8pm",
                                owner_email=email, email_verified=True))
    store.save_product(Product(id=f"{slug}-lapis", shop_id=shop.id, name="Kuih Lapis",
                               variants=[Variant(label="20 pcs", price=Decimal("16"))]))
    return shop


# --- Go live = create the account -------------------------------------------------------


def test_go_live_needs_shop_name_and_email(api, store):
    shop = draft(store)
    for body, word in [({"name": "X"}, "email"), ({"name": "X", "email": "not-an-email"}, "email"),
                       ({"email": "a@b.sg"}, "name"), ({"name": "  ", "email": "a@b.sg"}, "name")]:
        r = api.post(f"/api/shops/{shop.id}/publish", headers={"X-Owner-Key": KEY}, json=body)
        assert r.status_code == 400 and word in r.json()["detail"], body
    assert api.post(f"/api/shops/{shop.id}/publish", headers={"X-Owner-Key": KEY}).status_code == 400
    assert store.get_shop(shop.id).published is False


def test_go_live_creates_the_account_signs_in_and_emails_a_confirm_link(api, store, mail):
    shop = draft(store)
    r = go_live(api, shop)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shop"]["published"] is True  # live straight away
    assert body["shop"]["name"] == "Auntie Lim's Bakes"
    assert body["shop"]["owner_email"] == "siti.bakes@example.sg"
    assert body["shop"]["email_verified"] is False
    assert body["verify_sent_to"] == "siti.bakes@example.sg"
    assert body["owner_key"].startswith("kc_")  # the backup key

    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{owner_session.COOKIE}=")
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower() and "Secure" in cookie

    [email] = mail.sent
    assert email.to == "siti.bakes@example.sg"
    assert "Confirm" in email.subject
    assert "https://kc.example.sg/verify?token=" in email.text

    # Signed in by cookie: no key needed for this shop.
    assert api.get(f"/api/shops/{shop.id}").status_code == 200


def test_confirm_link_marks_the_email_verified_once(api, store, mail):
    shop = draft(store)
    go_live(api, shop)
    api.cookies.clear()
    token = token_in(mail.sent[0], "verify")
    r = api.post("/api/owner/verify", json={"token": token})
    assert r.status_code == 200
    assert r.json()["next"] == f"/shop/{shop.id}/orders"
    assert store.get_shop(shop.id).email_verified is True
    assert api.get(f"/api/shops/{shop.id}").status_code == 200  # and signed in
    again = api.post("/api/owner/verify", json={"token": token})
    assert again.status_code == 400 and "expired or was already used" in again.json()["detail"]


def test_resend_confirm_link_is_limited(api, store, mail):
    shop = draft(store)
    go_live(api, shop)
    codes = [api.post(f"/api/shops/{shop.id}/verify-email", headers=CSRF).status_code
             for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert len(mail.sent) == 4  # the first one plus three resends


# --- Sign in by email link ---------------------------------------------------------------


def test_email_link_signs_in_to_that_shop_only(api, store, mail):
    mine = live_shop(store, "siti@example.sg", "mine")
    other = live_shop(store, "someone@example.sg", "other")
    r = api.post("/api/owner/email-link", json={"email": " SITI@example.sg "})
    assert r.status_code == 200 and "sign-in link" in r.json()["message"]
    [email] = mail.sent
    assert email.to == "siti@example.sg" and "15 minutes" in email.text
    token = token_in(email, "signin")

    # Opening the link changes nothing (scanners follow links); the tap signs in.
    r = api.post("/api/owner/signin", json={"token": token})
    assert r.status_code == 200 and r.json()["shop_id"] == mine.id
    assert api.get(f"/api/shops/{mine.id}/orders").status_code == 200
    denied = api.get(f"/api/shops/{other.id}/orders")
    assert denied.status_code == 401 and "different shop" in denied.json()["detail"]
    assert api.get("/api/owner/session").json()["shop_id"] == mine.id

    # Single use.
    api.cookies.clear()
    assert api.post("/api/owner/signin", json={"token": token}).status_code == 400


def test_unknown_email_gets_the_same_answer_and_no_email(api, store, mail):
    live_shop(store, "siti@example.sg")
    r = api.post("/api/owner/email-link", json={"email": "nobody@example.sg"})
    assert r.status_code == 200
    assert r.json() == api.post("/api/owner/email-link", json={"email": "siti@example.sg"}).json()
    assert [e.to for e in mail.sent] == ["siti@example.sg"]
    assert api.post("/api/owner/email-link", json={"email": "nope"}).status_code == 400


def test_sign_in_links_expire_after_15_minutes_and_keep_their_purpose(store):
    shop = live_shop(store)
    now = utc_now()
    token = owner_session.issue_link(store, shop.id, "login", owner_session.LOGIN_LINK_TTL, now=now)
    assert owner_session.use_link(store, token, "login", now=now + timedelta(minutes=16)) is None
    token = owner_session.issue_link(store, shop.id, "login", owner_session.LOGIN_LINK_TTL, now=now)
    assert owner_session.use_link(store, token, "verify", now=now) is None  # wrong purpose...
    assert owner_session.use_link(store, token, "login", now=now) is None  # ...and used up
    assert owner_session.LOGIN_LINK_TTL == timedelta(minutes=15)


def test_email_links_are_rate_limited(app, store, mail):
    live_shop(store, "siti@example.sg")
    client = TestClient(app, client=("198.51.100.9", 1))
    same_email = [client.post("/api/owner/email-link", json={"email": "siti@example.sg"}).status_code
                  for _ in range(4)]
    assert same_email == [200, 200, 200, 429]
    other_ip = TestClient(app, client=("198.51.100.10", 1))
    many_emails = [other_ip.post("/api/owner/email-link", json={"email": f"a{i}@example.sg"}).status_code
                   for i in range(6)]
    assert many_emails == [200] * 5 + [429]


def test_bad_sign_in_tokens_count_towards_the_lockout(api):
    codes = [api.post("/api/owner/signin", json={"token": f"guess{i}"}).status_code for i in range(11)]
    assert codes == [400] * 10 + [429]


def test_session_cookie_writes_need_the_dashboard_header(api, store, mail):
    shop = draft(store)
    go_live(api, shop)
    r = api.patch(f"/api/shops/{shop.id}", json={"hours": "9am-5pm"})
    assert r.status_code == 403
    assert api.patch(f"/api/shops/{shop.id}", json={"hours": "9am-5pm"}, headers=CSRF).status_code == 200


def test_logout_ends_the_session(api, store, mail):
    shop = draft(store)
    go_live(api, shop)
    assert api.post("/api/owner/logout").status_code == 204
    api.cookies.clear()  # the browser drops it (Set-Cookie max-age=0); the server forgot it too
    assert api.get(f"/api/shops/{shop.id}").status_code == 401


def test_backup_key_still_signs_in(api, store):
    shop = live_shop(store)
    give_key(store, shop, "kc_backup")
    r = api.post("/api/owner/login", json={"key": "kc_backup"})
    assert r.status_code == 200 and owner_session.COOKIE in r.headers["set-cookie"]
    assert api.get(f"/api/shops/{shop.id}/orders").status_code == 200


def test_owner_email_is_never_public(api, store):
    live_shop(store, "siti@example.sg")
    assert "siti@example.sg" not in api.get("/api/public/shops/mak-kuih").text
    assert "siti@example.sg" not in api.get("/.well-known/ucp").text


# --- Order emails -----------------------------------------------------------------------


def place(store, settings, channel, **kw):
    async def go():
        order = await commerce.place_order(
            store, store.get_shop_by_slug("mak-kuih").id,
            kw.pop("items", [{"product_id": "mak-kuih-lapis", "variant": "20 pcs", "qty": 2}]),
            kw.pop("name", "Siti Rahman"), kw.pop("phone", "+65 9123 4567"),
            kw.pop("pickup", (now_sg() + timedelta(days=2)).replace(hour=10, minute=0)),
            kw.pop("note", ""), channel, kw.pop("agent", ""), settings=settings)
        await commerce.wait_for_background_tasks()
        return order
    return asyncio.run(go())


@pytest.mark.parametrize("channel, label", [(Channel.web, "Shop page"),
                                            (Channel.mcp, "AI assistant (MCP)"),
                                            (Channel.ucp, "AI agent (UCP)")])
def test_every_new_order_emails_the_owner(app, store, mail, channel, label):
    live_shop(store)
    place(store, app.state.settings, channel)  # first order from this phone
    order = place(store, app.state.settings, channel)
    email = mail.sent[-1]
    assert email.to == "owner@example.sg"
    assert order.status == "auto_approved" and email.subject.startswith("New order: Siti, S$32.00")
    for text in (email.text, email.html):
        assert "Kuih Lapis" in text and "S$32.00" in text and label in text
        assert "Siti" in text and "Rahman" not in text  # first name only
        assert "****4567" in text and "9123" not in text  # masked phone
    assert f"{(now_sg() + timedelta(days=2)):%a %d %b}, 10:00" in email.text
    assert "Review order" not in email.text
    assert email.idempotency_key == f"order-{order.id}"
    assert "owner_emailed" in [e.action for e in store.list_audit_events(order.shop_id)]


def test_held_order_email_says_why_and_its_button_signs_the_owner_in(app, api, store, mail):
    shop = live_shop(store)
    store.save_shop(shop.model_copy(update={"hours": "Tue-Sun 9am-6pm"}))
    monday = (now_sg() + timedelta(days=(7 - now_sg().weekday()) % 7 or 7)).replace(hour=10, minute=0)
    order = place(store, app.state.settings, Channel.mcp, pickup=monday, agent="Claude")
    assert order.status == "pending_approval"
    email = mail.sent[-1]
    assert email.subject.startswith("Action needed: Siti's order is waiting for you")
    assert "Why it's waiting" in email.text and "outside opening hours" in email.text
    assert "Review order" in email.html

    token = token_in(email, "signin")
    r = api.post("/api/owner/signin", json={"token": token})
    assert r.status_code == 200
    assert r.json()["next"] == f"/shop/{shop.id}/orders"
    approve = api.post(f"/api/shops/{shop.id}/orders/{order.id}/approve", headers=CSRF)
    assert approve.status_code == 200 and approve.json()["status"] == "approved"


def test_customer_text_in_order_emails_is_escaped(app, store, mail):
    live_shop(store)
    place(store, app.state.settings, Channel.web, name='<script>alert(1)</script> Tan')
    html = mail.sent[-1].html
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_failed_email_never_loses_the_order(app, store, mail, caplog):
    live_shop(store)
    mail.fail = True
    with caplog.at_level(logging.ERROR, logger="backend.mailer"):
        order = place(store, app.state.settings, Channel.web)
    assert store.get_order(order.id) is not None
    assert "owner_email_failed" in [e.action for e in store.list_audit_events(order.shop_id)]
    assert any("email failed" in r.message for r in caplog.records)
    assert not any("token=" in r.getMessage() for r in caplog.records)


def test_no_email_without_an_owner_email(app, store, mail):
    live_shop(store, email="")
    place(store, app.state.settings, Channel.web)
    assert mail.sent == []


# --- The Resend client ------------------------------------------------------------------


def test_resend_request_shape():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(url=str(request.url), auth=request.headers["authorization"],
                    idem=request.headers.get("idempotency-key"), body=json.loads(request.content))
        return httpx.Response(200, json={"id": "49a3999c"})

    sender = mailer.ResendMailer("re_test", "KampungCart <orders@kc.example.sg>",
                                 transport=httpx.MockTransport(handler))
    asyncio.run(sender.send(mailer.Email(to="a@b.sg", subject="Hi", text="t", html="<p>h</p>",
                                         idempotency_key="order-1", tags={"kind": "order"})))
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["auth"] == "Bearer re_test" and seen["idem"] == "order-1"
    assert seen["body"] == {"from": "KampungCart <orders@kc.example.sg>", "to": ["a@b.sg"],
                            "subject": "Hi", "text": "t", "html": "<p>h</p>",
                            "tags": [{"name": "kind", "value": "order"}]}


def test_resend_error_is_logged_not_raised(monkeypatch, caplog):
    sender = mailer.ResendMailer("re_test", "x@y.sg", transport=httpx.MockTransport(
        lambda r: httpx.Response(403, json={"message": "domain not verified"})))
    monkeypatch.setattr(mailer, "get_mailer", lambda s: sender)
    with caplog.at_level(logging.ERROR, logger="backend.mailer"):
        ok = asyncio.run(mailer.send_safely(Settings(_env_file=None), mailer.Email(
            to="siti@example.sg", subject="S", text="t", html="h")))
    assert ok is False
    assert "403" in caplog.text and "s***@example.sg" in caplog.text and "siti@" not in caplog.text


def test_no_api_key_means_log_only(monkeypatch):
    monkeypatch.undo()  # the real get_mailer, not the test fake
    assert isinstance(mailer.get_mailer(Settings(_env_file=None)), mailer.LogMailer)
    assert isinstance(mailer.get_mailer(Settings(_env_file=None, resend_api_key="re_x")),
                      mailer.ResendMailer)
