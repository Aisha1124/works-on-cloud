"""Sending email: Gmail SMTP (EMAIL_PROVIDER=smtp, the default) or Resend (EMAIL_PROVIDER=resend).
Without the chosen provider's credentials, emails are only logged.

Email never blocks or breaks the thing that triggered it: send_safely() catches every error
and logs it. Logs never contain links or tokens, only the subject and a masked recipient.
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Callable, Protocol

import httpx

from backend.api.config import Settings

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
RESEND_TEST_SENDER = "KampungCart <onboarding@resend.dev>"
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


def sender(settings: Settings) -> str:
    """EMAIL_FROM, or the provider's default sender."""
    if settings.email_from.strip():
        return settings.email_from.strip()
    if settings.email_provider == "smtp":
        return f"KampungCart <{settings.smtp_user.strip()}>"
    return RESEND_TEST_SENDER


class SmtpMailer:
    """SMTP with STARTTLS and login (Gmail: smtp.gmail.com:587 with an app password).
    smtplib blocks, so it runs in a worker thread."""

    def __init__(self, host: str, port: int, user: str, password: str, sender: str,
                 smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.sender = sender
        self.smtp_factory = smtp_factory  # tests pass a fake client

    def message(self, email: Email) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg["Message-ID"] = make_msgid(domain=self.user.partition("@")[2] or None)
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        return msg

    def _send(self, msg: EmailMessage) -> None:
        with self.smtp_factory(self.host, self.port, timeout=TIMEOUT_S) as smtp:
            smtp.starttls()
            smtp.login(self.user, self.password)
            smtp.send_message(msg)

    async def send(self, email: Email) -> None:
        await asyncio.to_thread(self._send, self.message(email))


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
    """The provider's credentials are missing: say what would have been sent, without the content."""

    def __init__(self, missing: str = "credentials"):
        self.missing = missing

    async def send(self, email: Email) -> None:
        log.info("email not sent (%s is empty): to=%s subject=%r",
                 self.missing, mask_email(email.to), email.subject)


def _secret(value) -> str:
    return value.get_secret_value().strip() if value else ""


def get_mailer(settings: Settings) -> Mailer:
    if settings.email_provider == "resend":
        key = _secret(settings.resend_api_key)
        return ResendMailer(key, sender(settings)) if key else LogMailer("RESEND_API_KEY")
    user, password = settings.smtp_user.strip(), _secret(settings.smtp_password)
    if not (user and password):
        return LogMailer("SMTP_USER or SMTP_PASSWORD")
    # Gmail shows app passwords in groups of four ("abcd efgh ..."); the spaces aren't part of it.
    return SmtpMailer(settings.smtp_host, settings.smtp_port, user, password.replace(" ", ""),
                      sender(settings))


async def send_safely(settings: Settings, email: Email) -> bool:
    """Send; on any failure log it and return False. Never raises."""
    try:
        await get_mailer(settings).send(email)
        return True
    except Exception as exc:  # noqa: BLE001 - email must never break an order or a login
        # SMTP errors (e.g. a refused recipient) can quote the address: mask it there too.
        error = str(exc).replace(email.to, mask_email(email.to))[:300]
        log.error("email failed: to=%s subject=%r error=%s: %s", mask_email(email.to),
                  email.subject, type(exc).__name__, error)
        return False
