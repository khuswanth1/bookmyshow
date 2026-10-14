"""Customer-support desk. Agents work tickets and look up bookings; they cannot move money or see QR secrets.

Refunds are escalated to an admin (least privilege): agents have no write access to payments or bookings.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.deps import CurrentUser, DB, PageParams, paginate, require_roles
from app.core.errors import not_found
from app.models import Booking, Payment, SupportMessage, SupportTicket, User
from app.schemas import (
    CustomerReplyIn, EscalateIn, HelpdeskPatch, HelpdeskReplyIn, SupportMessageOut, SupportOut,
)
from app.services.notify import notify
from app.services.platform import audit
from app.services.seats import utcnow

Agent = Annotated[User, Depends(require_roles("support", "admin"))]
router = APIRouter(prefix="/helpdesk", tags=["Support Desk"])
customer_router = APIRouter(tags=["User features, Stream & Support"])


def _msg_out(m: SupportMessage) -> SupportMessageOut:
    return SupportMessageOut(id=m.id, author_role=m.author_role, author_name=m.author.name if m.author else None,
                             body=m.body, is_internal=m.is_internal, created_at=m.created_at)


def _ticket_row(t: SupportTicket) -> dict:
    return {**SupportOut.model_validate(t).model_dump(), "assigned_to": t.assigned_to.name if t.assigned_to else None,
            "assigned_to_id": t.assigned_to_id, "user_id": t.user_id}


def _get(db, ticket_id: int) -> SupportTicket:
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise not_found("Ticket")
    return t


def booking_summary(db, b: Booking) -> dict:
    """Everything an agent needs to answer a query, and nothing secret (no QR token, no gateway ids)."""
    pay = db.scalar(select(Payment).where(Payment.booking_id == b.id).order_by(Payment.id.desc()).limit(1))
    title = b.event.title if b.event else (b.show.movie.title if b.show and b.show.movie else None)
    return {
        "code": b.code, "kind": b.kind, "status": b.status, "title": title,
        "starts_at": b.event.starts_at if b.event else (b.show.starts_at if b.show else None),
        "customer": {"id": b.user.id, "name": b.user.name, "email": b.user.email},
        "items": [f"{i.quantity} × {i.label}" for i in b.items],
        "total_paise": b.total_paise, "payable_paise": b.payable_paise, "refund_paise": b.refund_paise,
        "payment_status": pay.status if pay else None, "created_at": b.created_at, "confirmed_at": b.confirmed_at,
        "cancelled_at": b.cancelled_at, "checked_in_at": b.checked_in_at,
    }


# ------------------------------------------------------------------ agent endpoints
@router.get("/stats", summary="Queue overview")
def stats(user: Agent, db: DB):
    rows = dict(db.execute(select(SupportTicket.status, func.count()).group_by(SupportTicket.status)).all())
    open_ = SupportTicket.status != "resolved"
    return {"by_status": rows,
            "unassigned": db.scalar(select(func.count()).select_from(SupportTicket).where(
                SupportTicket.assigned_to_id.is_(None), open_)),
            "mine": db.scalar(select(func.count()).select_from(SupportTicket).where(
                SupportTicket.assigned_to_id == user.id, open_))}


@router.get("/tickets", summary="Ticket queue (most urgent first)")
def tickets(user: Agent, db: DB, page: PageParams,
            status: str | None = None, priority: str | None = None, category: str | None = None,
            assigned: Literal["me", "unassigned"] | None = None, q: str | None = Query(None, max_length=100)):
    stmt = select(SupportTicket)
    if status == "active":
        stmt = stmt.where(SupportTicket.status != "resolved")
    elif status:
        stmt = stmt.where(SupportTicket.status == status)
    if priority:
        stmt = stmt.where(SupportTicket.priority == priority)
    if category:
        stmt = stmt.where(SupportTicket.category == category)
    if assigned == "me":
        stmt = stmt.where(SupportTicket.assigned_to_id == user.id)
    elif assigned == "unassigned":
        stmt = stmt.where(SupportTicket.assigned_to_id.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(SupportTicket.subject.ilike(like), SupportTicket.email.ilike(like),
                              SupportTicket.booking_code.ilike(like)))
    rank = func.array_position(["urgent", "high", "normal", "low"], SupportTicket.priority)
    res = paginate(db, stmt.order_by(rank, SupportTicket.created_at), page)
    res["items"] = [_ticket_row(t) for t in res["items"]]
    return res


@router.get("/tickets/{ticket_id}", summary="Ticket thread with customer and booking context")
def ticket(ticket_id: int, user: Agent, db: DB):
    t = _get(db, ticket_id)
    customer = db.get(User, t.user_id) if t.user_id else None
    booking = None
    if t.booking_code:
        b = db.scalar(select(Booking).where(Booking.code == t.booking_code.strip().upper()))
        if b and customer and b.user_id == customer.id:  # never attach a stranger's booking to a ticket
            booking = booking_summary(db, b)
            audit(db, user, "helpdesk.booking_view", "booking", b.id, {"ticket_id": t.id})
            db.commit()
    return {**_ticket_row(t),
            "customer": ({"id": customer.id, "name": customer.name, "email": customer.email,
                          "email_verified": customer.email_verified, "joined": customer.created_at} if customer else None),
            "booking": booking,
            "messages": [_msg_out(m) for m in t.messages]}


@router.post("/tickets/{ticket_id}/messages", response_model=SupportMessageOut, status_code=201,
             summary="Reply to the customer, or leave an internal note")
def reply(ticket_id: int, body: HelpdeskReplyIn, user: Agent, db: DB):
    t = _get(db, ticket_id)
    m = SupportMessage(ticket_id=t.id, author_id=user.id, author_role="admin" if user.role == "admin" else "support",
                       body=body.body.strip(), is_internal=body.internal)
    db.add(m)
    if not body.internal:
        t.admin_reply = m.body
        if t.status == "open":
            t.status = "in_progress"
        if t.assigned_to_id is None:
            t.assigned_to_id = user.id
        if t.user_id:
            notify(db, t.user_id, f"Support replied: {t.subject}", m.body[:300], "support")
    audit(db, user, "helpdesk.note" if body.internal else "helpdesk.reply", "support_ticket", t.id)
    db.commit()
    db.refresh(m)
    return _msg_out(m)


@router.patch("/tickets/{ticket_id}", summary="Change status, priority or assignment")
def update_ticket(ticket_id: int, body: HelpdeskPatch, user: Agent, db: DB):
    t = _get(db, ticket_id)
    changes = body.model_dump(exclude_unset=True)
    if body.status:
        t.status = body.status
        t.resolved_at = utcnow() if body.status == "resolved" else None
    if body.priority:
        t.priority = body.priority
    if body.assign == "me":
        t.assigned_to_id = user.id
    elif body.assign == "none":
        t.assigned_to_id = None
    audit(db, user, "helpdesk.update", "support_ticket", t.id, changes)
    if body.status == "resolved" and t.user_id:
        notify(db, t.user_id, f"Ticket resolved: {t.subject}", "Reply on the ticket if you still need help.", "support")
    db.commit()
    db.refresh(t)
    return _ticket_row(t)


@router.post("/tickets/{ticket_id}/escalate-refund", summary="Ask an admin to approve a refund / cancellation")
def escalate_refund(ticket_id: int, body: EscalateIn, user: Agent, db: DB):
    t = _get(db, ticket_id)
    t.status, t.category = "escalated", "refund"
    if t.priority in ("low", "normal"):
        t.priority = "high"
    db.add(SupportMessage(ticket_id=t.id, author_id=user.id, author_role="admin" if user.role == "admin" else "support",
                          body=f"Refund escalated to admin: {body.reason.strip()}", is_internal=True))
    for admin_id in db.scalars(select(User.id).where(User.role == "admin", User.is_active)):
        notify(db, admin_id, f"Refund escalation: ticket #{t.id}",
               f"{user.name} asked for a refund review ({t.booking_code or 'no booking code'}): {body.reason.strip()[:200]}",
               "support")
    audit(db, user, "helpdesk.escalate_refund", "support_ticket", t.id, {"booking_code": t.booking_code})
    db.commit()
    return {"message": "Escalated to an admin", "status": t.status}


@router.get("/bookings/lookup", summary="Find a booking by its code (every lookup is audit-logged)")
def lookup(code: Annotated[str, Query(min_length=4, max_length=20)], user: Agent, db: DB):
    b = db.scalar(select(Booking).where(Booking.code == code.strip().upper()))
    if not b:
        raise not_found("Booking")
    audit(db, user, "helpdesk.booking_lookup", "booking", b.id)
    db.commit()
    return booking_summary(db, b)


# ------------------------------------------------------------------ customer side of the thread
def _own(db, user: User, ticket_id: int) -> SupportTicket:
    t = db.get(SupportTicket, ticket_id)
    if not t or not (t.user_id == user.id or t.email == user.email.lower()):
        raise not_found("Ticket")
    return t


@customer_router.get("/support/tickets/{ticket_id}", summary="One of my tickets, with the public conversation")
def my_ticket(ticket_id: int, user: CurrentUser, db: DB):
    t = _own(db, user, ticket_id)
    return {**SupportOut.model_validate(t).model_dump(),
            "messages": [_msg_out(m) for m in t.messages if not m.is_internal]}


@customer_router.post("/support/tickets/{ticket_id}/messages", response_model=SupportMessageOut, status_code=201,
                      summary="Reply on my ticket")
def my_reply(ticket_id: int, body: CustomerReplyIn, user: CurrentUser, db: DB):
    t = _own(db, user, ticket_id)
    m = SupportMessage(ticket_id=t.id, author_id=user.id, author_role="customer", body=body.body.strip())
    db.add(m)
    if t.status in ("resolved", "waiting_customer"):
        t.status, t.resolved_at = "open", None
    if t.assigned_to_id:
        notify(db, t.assigned_to_id, f"Customer replied: ticket #{t.id}", m.body[:200], "support")
    db.commit()
    db.refresh(m)
    return _msg_out(m)
