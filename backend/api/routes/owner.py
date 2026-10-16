"""Owner sign-in: by email link (main way) or by backup key. Both end in a session cookie that
opens exactly one shop."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend import emails, mailer, owner_session
from backend.api.deps import caller, check_not_locked_out, record_failed_key
from backend.audit import log_event
from backend.models import Actor, Shop
from backend.owner_auth import MAX_KEY_LEN, shop_for_key

router = APIRouter(prefix="/api/owner")

LOGIN_FAILED = "That key doesn't match any shop. Check it (it starts with kc_) and try again."
LINK_SENT = ("If that email has a shop on KampungCart, we've sent a sign-in link. "
             "It works once and expires in 15 minutes.")
LINK_BAD = "This link has expired or was already used. Ask for a new one below."
LINK_IP_LIMIT, LINK_EMAIL_LIMIT, LINK_WINDOW_S = 5, 3, 900.0


class KeyLoginBody(BaseModel):
    key: str = Field(max_length=MAX_KEY_LEN)


class EmailBody(BaseModel):
    email: str = Field(max_length=owner_session.MAX_EMAIL_LEN)


class TokenBody(BaseModel):
    token: str = Field(max_length=200)


class SignedIn(BaseModel):
    shop_id: str
    name: str
    slug: str
    published: bool
    next: str = ""


def _signed_in(shop: Shop, next_path: str = "") -> SignedIn:
    return SignedIn(shop_id=shop.id, name=shop.name, slug=shop.slug, published=shop.published,
                    next=next_path or f"/shop/{shop.id}/orders")


@router.post("/login", response_model=SignedIn)
def login_with_key(request: Request, response: Response, body: KeyLoginBody) -> SignedIn:
    """Backup key -> a session for its shop. Wrong keys count towards the per-client limit."""
    check_not_locked_out(request)
    store = request.app.state.store
    shop_id = shop_for_key(store, body.key.strip())
    shop = store.get_shop(shop_id) if shop_id else None
    if shop is None:
        record_failed_key(request)
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)
    owner_session.start_session(store, response, request.app.state.settings, shop.id)
    return _signed_in(shop)


@router.post("/email-link")
def send_login_link(request: Request, background: BackgroundTasks, body: EmailBody) -> dict:
    """Email a one-time sign-in link (15 minutes) for each shop of this email. The answer is
    the same whether or not the email has a shop, so nobody can probe for owners."""
    email = owner_session.normalize_email(body.email)
    if email is None:
        raise HTTPException(status_code=400, detail="That doesn't look like an email address.")
    state = request.app.state
    if not state.link_ip_limiter.allow(caller(request)) or not state.link_email_limiter.allow(email):
        raise HTTPException(status_code=429,
                            detail="We've sent a few links already. Check your inbox and spam folder, "
                                   "or try again in 15 minutes.")
    store, settings = state.store, state.settings
    shops = store.find_shops_by_owner_email(email)
    if shops:
        links = [(shop, owner_session.link_url(settings, "signin", owner_session.issue_link(
            store, shop.id, "login", owner_session.LOGIN_LINK_TTL))) for shop in shops]
        background.add_task(mailer.send_safely, settings, emails.login_email(email, links))
    return {"message": LINK_SENT}


@router.post("/signin", response_model=SignedIn)
def sign_in_with_link(request: Request, response: Response, body: TokenBody) -> SignedIn:
    """The tap on "Open my dashboard" after opening a sign-in link. Single use."""
    check_not_locked_out(request)
    store = request.app.state.store
    row = owner_session.use_link(store, body.token, "login")
    shop = store.get_shop(row["shop_id"]) if row else None
    if shop is None:
        record_failed_key(request)
        raise HTTPException(status_code=400, detail=LINK_BAD)
    owner_session.start_session(store, response, request.app.state.settings, shop.id)
    return _signed_in(shop, row.get("next", ""))


@router.post("/verify", response_model=SignedIn)
def verify_email(request: Request, response: Response, body: TokenBody) -> SignedIn:
    """The tap on "Confirm my email". Marks the email confirmed and signs the owner in."""
    check_not_locked_out(request)
    store = request.app.state.store
    row = owner_session.use_link(store, body.token, "verify")
    shop = store.get_shop(row["shop_id"]) if row else None
    if shop is None:
        record_failed_key(request)
        raise HTTPException(status_code=400, detail=LINK_BAD)
    if not shop.email_verified:
        shop = store.save_shop(shop.model_copy(update={"email_verified": True}))
        log_event(store, shop_id=shop.id, actor=Actor.owner, action="email_verified",
                  entity_type="shop", entity_id=shop.id,
                  summary=f"Owner confirmed their email ({mailer.mask_email(shop.owner_email)})",
                  details={})
    owner_session.start_session(store, response, request.app.state.settings, shop.id)
    return _signed_in(shop, row.get("next", ""))


@router.get("/session", response_model=SignedIn)
def current_session(request: Request) -> SignedIn:
    """Which shop this browser is signed in to (401 if none)."""
    store = request.app.state.store
    shop_id = owner_session.session_shop(store, request.cookies.get(owner_session.COOKIE))
    shop = store.get_shop(shop_id) if shop_id else None
    if shop is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return _signed_in(shop)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    owner_session.end_session(request.app.state.store, response,
                              request.cookies.get(owner_session.COOKIE))
    response.status_code = 204
    return response
