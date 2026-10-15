"""Owner routes for orders and the audit log."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agents.approval import service as approval
from backend.api.deps import require_owner
from backend.models import AuditEvent, Order, OrderStatus

router = APIRouter(prefix="/api/shops/{shop_id}", dependencies=[Depends(require_owner)])


class RejectBody(BaseModel):
    reason: str = Field(default="", max_length=approval.MAX_REASON_LEN)


class AuditPage(BaseModel):
    events: list[AuditEvent]
    limit: int
    offset: int


def _store(request: Request, shop_id: str):
    store = request.app.state.store
    if store.get_shop(shop_id) is None:
        raise HTTPException(status_code=404, detail="Shop not found.")
    return store


def _order_or_404(store, shop_id: str, order_id: str) -> Order:
    try:
        return approval.get_shop_order(store, shop_id, order_id)
    except approval.OrderNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/orders", response_model=list[Order])
def list_orders(request: Request, shop_id: str, status: OrderStatus | None = None) -> list[Order]:
    """Newest first. ?status=pending_approval shows what needs the owner."""
    return _store(request, shop_id).list_orders(shop_id, status)


@router.get("/orders/{order_id}", response_model=Order)
def get_order(request: Request, shop_id: str, order_id: str) -> Order:
    return _order_or_404(_store(request, shop_id), shop_id, order_id)


@router.post("/orders/{order_id}/approve", response_model=Order)
def approve_order(request: Request, shop_id: str, order_id: str) -> Order:
    store = _store(request, shop_id)
    _order_or_404(store, shop_id, order_id)
    try:
        return approval.approve(store, shop_id, order_id)
    except approval.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/orders/{order_id}/reject", response_model=Order)
def reject_order(
    request: Request, shop_id: str, order_id: str, body: RejectBody | None = None
) -> Order:
    store = _store(request, shop_id)
    _order_or_404(store, shop_id, order_id)
    try:
        return approval.reject(store, shop_id, order_id, body.reason if body else "")
    except approval.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/audit", response_model=AuditPage)
def list_audit(
    request: Request, shop_id: str,
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
) -> AuditPage:
    """Newest first."""
    events = _store(request, shop_id).list_audit_events(shop_id, limit=limit, offset=offset)
    return AuditPage(events=events, limit=limit, offset=offset)
