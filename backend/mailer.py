"""Sending email. Resend in production (RESEND_API_KEY); without a key, emails are only logged.

Email never blocks or breaks the thing that triggered it: send_safely() catches every error
and logs it. Logs never contain links or tokens, only the subject and a masked recipient.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from backend.api.config import Settings

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_S = 10.0


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str
    # Resend Idempotency-Key: the same key within 24h never sends twice.
    idempotency_key: str = ""
    tags: dict[str, str] = field(default_factory=dict)


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


def mask_email(address: str) -> str:
    """'siti.bakes@gmail.com' -> 's***@gmail.com', for logs."""
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


class ResendMailer:
    def __init__(self, api_key: str, sender: str, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key
        self.sender = sender
        self.transport = transport  # tests pass a mock transport; production uses the network

    async def send(self, email: Email) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if email.idempotency_key:
            headers["Idempotency-Key"] = email.idempotency_key[:256]
        body = {"from": self.sender, "to": [email.to], "subject": email.subject,
                "text": email.text, "html": email.html}
        if email.tags:
            body["tags"] = [{"name": k, "value": v} for k, v in email.tags.items()]
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=self.transport) as client:
            res = await client.post(RESEND_URL, json=body, headers=headers)
        if res.status_code >= 300:
            # Resend's error body names the problem (e.g. unverified domain); no secrets in it.
            raise RuntimeError(f"Resend HTTP {res.status_code}: {res.text[:300]}")


class LogMailer:
    """No RESEND_API_KEY: say what would have been sent, without the content."""

    async def send(self, email: Email) -> None:
        log.info("email not sent (RESEND_API_KEY is empty): to=%s subject=%r",
                 mask_email(email.to), email.subject)


def get_mailer(settings: Settings) -> Mailer:
    key = settings.resend_api_key.get_secret_value().strip() if settings.resend_api_key else ""
    return ResendMailer(key, settings.email_from) if key else LogMailer()


async def send_safely(settings: Settings, email: Email) -> bool:
    """Send; on any failure log it and return False. Never raises."""
    try:
        await get_mailer(settings).send(email)
        return True
    except Exception as exc:  # noqa: BLE001 - email must never break an order or a login
        log.error("email failed: to=%s subject=%r error=%s", mask_email(email.to),
                  email.subject, str(exc)[:300])
        return False
