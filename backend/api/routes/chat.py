"""The "Order with AI" chat on the shop page: POST /api/public/shops/{slug}/chat.

Each message goes to the KampungCart Shop Assistant (agents/shopper/assistant.py), which
orders through the shop's MCP tools. Limited per client and site-wide, so the cost stays
small. Every failure is one friendly sentence; the normal order form never depends on this.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agents.shopper import assistant
from backend.api.deps import caller
from backend.external import ShopNotFound, published_shop

log = logging.getLogger(__name__)
router = APIRouter()

CHAT_IP_LIMIT, CHAT_IP_WINDOW_S = 30, 900.0  # messages per client per 15 minutes
CHAT_SITE_LIMIT, CHAT_SITE_WINDOW_S = 300, 3600.0  # messages for the whole site per hour
TOO_MANY = ("You've sent a lot of messages. Please wait a few minutes, or order with the "
            "form below.")
SITE_BUSY = ("The AI assistant is very busy right now. Please try again later, or order with "
             "the form below.")


class ChatIn(BaseModel):
    chat_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=assistant.MAX_MESSAGE_LEN)


class ChatOrder(BaseModel):
    order_id: str
    status: str  # buyer words: confirmed | pending_owner_approval | rejected | ...
    status_url: str
    subtotal: str
    pickup_time: str


class ChatOut(BaseModel):
    chat_id: str
    reply: str
    orders: list[ChatOrder]
    turns_left: int


@router.post("/api/public/shops/{slug}/chat", response_model=ChatOut)
async def chat(request: Request, slug: str, body: ChatIn) -> ChatOut:
    state = request.app.state
    try:
        shop = published_shop(state.store, slug)
    except ShopNotFound:
        raise HTTPException(status_code=404, detail="This shop isn't open on KampungCart.") from None
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Please type a message.")
    who = caller(request)
    if not state.chat_ip_limiter.allow(who):
        raise HTTPException(status_code=429, detail=TOO_MANY)
    if not state.chat_site_limiter.allow("all"):
        raise HTTPException(status_code=429, detail=SITE_BUSY)
    try:
        out = await state.shop_assistant.reply(shop, body.chat_id, message, who)
    except assistant.ChatUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except (assistant.ChatGone, assistant.ChatFull) as exc:  # the page offers a new chat
        raise HTTPException(status_code=410, detail=str(exc)) from None
    except assistant.ChatBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:  # never a stack trace in the page
        log.exception("chat failed")
        raise HTTPException(status_code=502, detail=assistant.FAILED) from None
    return ChatOut(chat_id=out.chat_id, reply=out.reply,
                   orders=[ChatOrder(**o) for o in out.orders], turns_left=out.turns_left)
