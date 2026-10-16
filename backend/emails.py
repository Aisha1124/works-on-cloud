"""The emails KampungCart sends to shop owners: confirm email, sign-in link, new order.

Plain text plus simple inline-styled HTML (what email apps support). Everything that comes from
a customer or an agent is escaped and kept short; it is data, never markup.
"""

import html
from decimal import Decimal

from backend.external import mask_phone
from backend.mailer import Email
from backend.models import Channel, Order, OrderStatus, Shop
from backend.timeutil import to_sg

INK, PAPER, CHILI, TURMERIC = "#1C1A17", "#FFFDF8", "#D7261E", "#F2B705"

CHANNEL_LABEL = {
    Channel.web: "Shop page",
    Channel.mcp: "AI assistant (MCP)",
    Channel.ucp: "AI agent (UCP)",
    Channel.dashboard: "Dashboard",
}


def _e(text: str) -> str:
    return html.escape(text or "", quote=True)


def _one_line(text: str, limit: int = 60) -> str:
    return " ".join((text or "").split())[:limit]


def _page(title: str, body_html: str) -> str:
    return (
        f'<div style="background:#F4EDE1;padding:24px;font-family:Arial,Helvetica,sans-serif;color:{INK}">'
        f'<div style="max-width:520px;margin:0 auto;background:{PAPER};border:2px solid {INK};padding:20px">'
        f'<p style="margin:0 0 4px;font-weight:800;font-size:18px">Kampung<span style="color:{CHILI}">Cart</span></p>'
        f'<h1 style="margin:8px 0 16px;font-size:22px">{_e(title)}</h1>{body_html}</div></div>'
    )


def _button(url: str, label: str) -> str:
    return (f'<p style="margin:20px 0"><a href="{_e(url)}" style="display:inline-block;background:{CHILI};'
            f'color:#fff;font-weight:700;text-decoration:none;padding:12px 18px;border:2px solid {INK}">'
            f"{_e(label)}</a></p>")


def money(value: Decimal) -> str:
    return f"S${value:.2f}"


# --- confirm email ----------------------------------------------------------------------


def verify_email(shop: Shop, url: str) -> Email:
    subject = f"Confirm your email for {_one_line(shop.name)}"
    text = (f"Your shop {shop.name} is live on KampungCart.\n\n"
            f"Confirm this is your email, so we can send you orders and sign-in links:\n{url}\n\n"
            "If you didn't create this shop, ignore this email.")
    body = (f"<p>Your shop <b>{_e(shop.name)}</b> is live on KampungCart.</p>"
            "<p>Confirm this is your email, so we can send you orders and sign-in links.</p>"
            f"{_button(url, 'Confirm my email')}"
            '<p style="font-size:13px;color:#5C544A">If you didn\'t create this shop, ignore this email.</p>')
    return Email(to=shop.owner_email, subject=subject, text=text,
                 html=_page("Confirm your email", body), tags={"kind": "verify"})


# --- sign-in link -----------------------------------------------------------------------


def login_email(to: str, shops_and_urls: list[tuple[Shop, str]]) -> Email:
    many = len(shops_and_urls) > 1
    lines = "\n".join(f"{shop.name}: {url}" for shop, url in shops_and_urls)
    text = ("Tap to open your shop on KampungCart. The link works once and expires in 15 minutes.\n\n"
            f"{lines}\n\nIf you didn't ask to sign in, ignore this email.")
    buttons = "".join(_button(url, f"Open {shop.name}" if many else "Open my shop")
                      for shop, url in shops_and_urls)
    body = ("<p>Tap to open your shop. The link works once and expires in 15 minutes.</p>"
            f"{buttons}"
            '<p style="font-size:13px;color:#5C544A">If you didn\'t ask to sign in, ignore this email.</p>')
    return Email(to=to, subject="Your KampungCart sign-in link", text=text,
                 html=_page("Sign in to KampungCart", body), tags={"kind": "login"})


# --- new order --------------------------------------------------------------------------


def hold_reasons(order: Order) -> list[str]:
    """Why the owner must look at a held order, in plain English."""
    if order.review_reasons:
        return list(order.review_reasons)
    if order.risk and order.risk.reasons:
        return list(order.risk.reasons)
    return ["This order needs your OK before it is confirmed."]


def order_email(shop: Shop, order: Order, review_url: str) -> Email:
    held = order.status == OrderStatus.pending_approval
    first = _one_line(order.customer_name.split()[0] if order.customer_name.split() else "A customer", 40)
    pickup = f"{to_sg(order.pickup_at):%a %d %b, %H:%M}"
    channel = CHANNEL_LABEL.get(order.channel, str(order.channel))
    phone = mask_phone(order.customer_phone)
    subject = (f"Action needed: {first}'s order is waiting for you ({money(order.total)})" if held
               else f"New order: {first}, {money(order.total)}, pickup {pickup}")

    item_lines = [f"{line.qty} x {line.name}" + (f" ({line.variant})" if line.variant else "")
                  + "".join(f", {v}" for v in line.options.values())
                  + f" ... {money(line.line_total)}" for line in order.items]
    item_lines += [f"{u.qty} x {u.name} (not on your menu, no price yet)"
                   for u in order.unpriced_requests]
    reasons = hold_reasons(order) if held else []

    text = "\n".join([
        f"{'Held for your OK' if held else 'Confirmed automatically'} - order {order.id}",
        "",
        *item_lines,
        f"Total: {money(order.total)} (pay at pickup)",
        f"Pickup: {pickup}",
        f"Customer: {first}, phone {phone}",
        f"Ordered via: {channel}",
        *(["", "Why it's waiting:", *(f"- {r}" for r in reasons)] if held else []),
        "",
        f"{'Review order' if held else 'See your orders'}: {review_url}",
    ])

    rows = "".join(
        f'<tr><td style="padding:4px 0">{_e(t.rsplit(" ... ", 1)[0])}</td>'
        f'<td style="padding:4px 0;text-align:right;font-family:monospace">'
        f'{_e(t.rsplit(" ... ", 1)[1]) if " ... " in t else "-"}</td></tr>' for t in item_lines)
    reason_html = ("" if not held else
                   f'<div style="background:#FBE7A1;border:2px solid {INK};padding:10px 12px;margin:12px 0">'
                   "<b>Why it's waiting for you</b><ul style=\"margin:6px 0 0;padding-left:18px\">"
                   + "".join(f"<li>{_e(r)}</li>" for r in reasons) + "</ul></div>")
    body = (
        f'<p style="margin:0 0 12px"><span style="border:2px solid {INK};padding:2px 8px;font-weight:700;'
        f'background:{TURMERIC if held else "#CDE8D6"}">{"HELD" if held else "CONFIRMED"}</span>'
        f' <span style="font-family:monospace;font-size:13px">order {_e(order.id)}</span></p>'
        f'<table style="width:100%;border-collapse:collapse;border-top:2px dashed {INK};'
        f'border-bottom:2px dashed {INK}">{rows}'
        f'<tr><td style="padding:6px 0;font-weight:700">TOTAL</td><td style="padding:6px 0;'
        f'text-align:right;font-family:monospace;font-weight:700">{money(order.total)}</td></tr></table>'
        f'<p style="margin:12px 0 0">Pickup: <b>{_e(pickup)}</b> · pay at pickup<br>'
        f"Customer: <b>{_e(first)}</b>, phone {_e(phone)}<br>Ordered via: {_e(channel)}</p>"
        f"{reason_html}"
        f"{_button(review_url, 'Review order' if held else 'See your orders')}"
    )
    title = "An order is waiting for your OK" if held else "New order"
    return Email(to=shop.owner_email, subject=subject, text=text, html=_page(title, body),
                 idempotency_key=f"order-{order.id}", tags={"kind": "order"})
