"""Audit log helper. Every feature that changes something calls log_event."""

from typing import Any

from backend.models import Actor, AuditEvent
from backend.store.base import Store


def log_event(
    store: Store,
    *,
    shop_id: str,
    actor: Actor | str,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        shop_id=shop_id,
        actor=Actor(actor),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        details=details or {},
    )
    return store.add_audit_event(event)
