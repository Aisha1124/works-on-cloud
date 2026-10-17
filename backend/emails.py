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


def _item_lines(order: Order) -> list[str]:
    return [f"{line.qty} x {line.name}" + (f" ({line.variant})" if line.variant else "")
            + f" ... {money(line.line_total)}" for line in order.items]


# --- customer updates ---------------------------------------------------------------------

# kind -> (subject start, stamp word, stamp colour, headline)
CUSTOMER_KINDS = {
    "confirmed": ("Confirmed", "CONFIRMED", "#CDE8D6", "Your order is confirmed"),
    "rejected": ("Not accepted", "REJECTED", "#F6C9C6", "The shop couldn't take your order"),
    "expired": ("Not accepted", "EXPIRED", "#F6C9C6", "The shop didn't respond in time"),
    "cancelled": ("Cancelled", "CANCELLED", "#F6C9C6", "Your order is cancelled"),
}


def customer_email(shop: Shop, order: Order, kind: str, status_url: str) -> Email:
    """A status update to the customer who left their email. kind: CUSTOMER_KINDS key."""
    start, stamp, colour, headline = CUSTOMER_KINDS[kind]
    shop_name = _one_line(shop.name)
    pickup = f"{to_sg(order.pickup_at):%a %d %b, %H:%M}"
    subject = f"{start}: your order from {shop_name} (pickup {pickup})"
    if kind == "confirmed":
        lead = f"See you at pickup on {pickup}. Please pay the shop when you collect."
    elif kind == "rejected":
        lead = "Sorry, the shop can't make this order."
    elif kind == "expired":
        lead = "The shop didn't reply in time, so this order is cancelled. You won't be charged."
    else:
        lead = "Your order is cancelled. The shop has been told. You won't be charged."
    reason = order.rejection_reason if kind == "rejected" else ""
    items = _item_lines(order)
    text = "\n".join([
        f"{headline} - {shop_name}, order {order.id}", "", lead,
        *([f"Reason from the shop: {reason}"] if reason else []), "", *items,
        f"Total: {money(order.total)} (pay at pickup)", f"Pickup: {pickup}", "",
        f"Check your order: {status_url}",
    ])
    rows = "".join(
        f'<tr><td style="padding:4px 0">{_e(t.rsplit(" ... ", 1)[0])}</td>'
        f'<td style="padding:4px 0;text-align:right;font-family:monospace">'
        f'{_e(t.rsplit(" ... ", 1)[1])}</td></tr>' for t in items)
    body = (
        f'<p style="margin:0 0 12px"><span style="border:2px solid {INK};padding:2px 8px;'
        f'font-weight:700;background:{colour}">{stamp}</span> <span style="font-family:monospace;'
        f'font-size:13px">{_e(shop_name)} · order {_e(order.id)}</span></p>'
        f"<p>{_e(lead)}</p>"
        + (f"<p>Reason from the shop: <b>{_e(reason)}</b></p>" if reason else "")
        + f'<table style="width:100%;border-collapse:collapse;border-top:2px dashed {INK};'
        f'border-bottom:2px dashed {INK}">{rows}'
        f'<tr><td style="padding:6px 0;font-weight:700">TOTAL</td><td style="padding:6px 0;'
        f'text-align:right;font-family:monospace;font-weight:700">{money(order.total)}</td></tr>'
        f'</table><p style="margin:12px 0 0">Pickup: <b>{_e(pickup)}</b> · pay at pickup</p>'
        f"{_button(status_url, 'Check my order')}"
    )
    return Email(to=order.customer_email, subject=subject, text=text,
                 html=_page(headline, body), idempotency_key=f"customer-{kind}-{order.id}",
                 tags={"kind": f"customer_{kind}"})


def report_email(to: str, shop: Shop, shop_url: str, reason: str, details: str,
                 reporter_email: str) -> Email:
    """A "report this shop" message for the person who runs this KampungCart. Everything from
    the reporter is untrusted text: escaped, never followed."""
    subject = f"Shop reported: {_one_line(shop.name)} ({reason})"
    reply = reporter_email or "not given"
    text = "\n".join([f"Someone reported {shop.name} ({shop_url}).", "", f"Reason: {reason}",
                      f"Details: {details or '(none)'}", f"Reporter's email: {reply}", "",
                      f"Shop id: {shop.id}, owner email: {shop.owner_email or '(none)'}"])
    body = (f"<p>Someone reported <b>{_e(shop.name)}</b> "
            f'(<a href="{_e(shop_url)}">{_e(shop_url)}</a>).</p>'
            f"<p><b>Reason:</b> {_e(reason)}</p>"
            f'<p><b>Details:</b></p><p style="white-space:pre-wrap;border-left:4px solid {INK};'
            f'padding-left:10px">{_e(details) or "(none)"}</p>'
            f"<p><b>Reporter's email:</b> {_e(reply)}</p>"
            f'<p style="font-size:13px;color:#5C544A">Shop id {_e(shop.id)} · owner email '
            f"{_e(shop.owner_email or '(none)')}</p>")
    return Email(to=to, subject=subject, text=text, html=_page("A shop was reported", body),
                 tags={"kind": "shop_report"})


def owner_cancelled_email(shop: Shop, order: Order, orders_url: str) -> Email:
    first = _one_line(order.customer_name.split()[0] if order.customer_name.split() else "A customer", 40)
    pickup = f"{to_sg(order.pickup_at):%a %d %b, %H:%M}"
    subject = f"Cancelled: {first}'s order for {pickup} ({money(order.total)})"
    items = _item_lines(order)
    text = "\n".join([f"{first} cancelled order {order.id}. No need to prepare it.", "",
                      *items, f"Pickup was: {pickup}", "", f"See your orders: {orders_url}"])
    body = (f"<p><b>{_e(first)}</b> cancelled order <span style=\"font-family:monospace\">"
            f"{_e(order.id)}</span>. No need to prepare it.</p>"
            + "".join(f"<p style=\"margin:2px 0\">{_e(t)}</p>" for t in items)
            + f"<p>Pickup was: <b>{_e(pickup)}</b></p>{_button(orders_url, 'See your orders')}")
    return Email(to=shop.owner_email, subject=subject, text=text,
                 html=_page("An order was cancelled", body),
                 idempotency_key=f"owner-cancelled-{order.id}", tags={"kind": "owner_cancelled"})
