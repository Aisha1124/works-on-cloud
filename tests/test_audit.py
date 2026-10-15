import pytest

from backend.audit import log_event
from backend.models import Actor


def test_log_event_persists_and_lists_newest_first(store):
    first = log_event(
        store, shop_id="s1", actor="catalog_agent", action="catalog.extracted",
        entity_type="shop", entity_id="s1", summary="Read 12 items from photo",
        details={"items": 12},
    )
    second = log_event(
        store, shop_id="s1", actor=Actor.owner, action="shop.published",
        entity_type="shop", entity_id="s1", summary="Owner published the shop",
    )
    log_event(
        store, shop_id="other", actor="system", action="x",
        entity_type="shop", entity_id="other", summary="Other shop",
    )

    events = store.list_audit_events("s1")
    assert [e.id for e in events] == [second.id, first.id]
    assert events[1].actor == Actor.catalog_agent
    assert events[1].details == {"items": 12}
    assert events[0].details == {}
    assert len(store.list_audit_events("s1", limit=1)) == 1


def test_log_event_rejects_unknown_actor(store):
    with pytest.raises(ValueError):
        log_event(
            store, shop_id="s1", actor="hacker", action="x",
            entity_type="shop", entity_id="s1", summary="nope",
        )


def test_audit_events_paginate_with_offset(store):
    ids = [
        log_event(
            store, shop_id="s1", actor="system", action=f"a{i}",
            entity_type="shop", entity_id="s1", summary=f"event {i}",
        ).id
        for i in range(5)
    ]
    newest_first = list(reversed(ids))
    assert [e.id for e in store.list_audit_events("s1", limit=2)] == newest_first[:2]
    assert [e.id for e in store.list_audit_events("s1", limit=2, offset=2)] == newest_first[2:4]
    assert [e.id for e in store.list_audit_events("s1", limit=2, offset=4)] == newest_first[4:]
    assert store.list_audit_events("s1", limit=2, offset=10) == []
