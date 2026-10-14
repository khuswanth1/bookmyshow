"""Seat layout, per-show seat materialisation, and concurrency-safe seat locking."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, conflict, not_found
from app.models import Screen, Seat, Show, ShowSeat
from app.services.platform import show_is_public
from app.services.realtime import publish_seats


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_seats(db: Session, screen: Screen, sync_if_shows: bool = False) -> int:
    """(Re)create the physical seats of a screen from screen.layout.

    With existing shows this refuses (409), unless sync_if_shows (admin edits) asks for an in-place sync instead."""
    if db.scalar(select(func.count()).select_from(Show).where(Show.screen_id == screen.id)):
        if sync_if_shows:
            return sync_seats(db, screen)
        raise AppError(409, "screen_in_use", "Cannot change the layout of a screen that already has shows")
    db.execute(delete(Seat).where(Seat.screen_id == screen.id))
    rows = (screen.layout or {}).get("rows", [])
    seats = []
    for idx, row in enumerate(rows):
        for n in range(1, int(row["seats"]) + 1):
            seats.append(
                Seat(screen_id=screen.id, row_label=row["label"], number=n, category=row["category"], row_index=idx)
            )
    db.add_all(seats)
    db.flush()
    return len(seats)


def sync_seats(db: Session, screen: Screen) -> int:
    """Apply a new layout to a screen that already has shows, keeping existing seats (and their bookings) in place.

    Seats that disappear or change category are refused (409) if any show has them locked or booked; otherwise their
    per-show rows are removed / re-categorised. New seats get per-show rows for every show with a price for their category.
    """
    desired: dict[tuple[str, int], tuple[str, int]] = {}
    for idx, row in enumerate((screen.layout or {}).get("rows", [])):
        for n in range(1, int(row["seats"]) + 1):
            desired[(row["label"], n)] = (row["category"], idx)

    existing = {(s.row_label, s.number): s for s in db.scalars(select(Seat).where(Seat.screen_id == screen.id))}
    busy = set(db.scalars(
        select(ShowSeat.seat_id).join(Show, Show.id == ShowSeat.show_id)
        .where(Show.screen_id == screen.id, or_(ShowSeat.status == "booked", ShowSeat.status == "locked", ShowSeat.booking_id.is_not(None)))
        .distinct()
    ))

    removed = [s for k, s in existing.items() if k not in desired]
    recat = [s for k, s in existing.items() if k in desired and desired[k][0] != s.category]
    clash = sorted(f"{s.row_label}{s.number}" for s in removed + recat if s.id in busy)
    if clash:
        raise AppError(409, "seats_in_use", f"Seats {', '.join(clash[:8])}{'…' if len(clash) > 8 else ''} are booked or held in a show, so they can't be removed or moved to another category")

    if removed:
        db.execute(delete(Seat).where(Seat.id.in_([s.id for s in removed])))  # show_seats cascade
    for s in recat:
        s.category = desired[(s.row_label, s.number)][0]
        db.execute(update(ShowSeat).where(ShowSeat.seat_id == s.id).values(category=s.category))
    for k, s in existing.items():
        if k in desired:
            s.row_index = desired[k][1]
    db.add_all(
        Seat(screen_id=screen.id, row_label=k[0], number=k[1], category=cat, row_index=idx)
        for k, (cat, idx) in desired.items() if k not in existing
    )
    db.flush()
    for show in db.scalars(select(Show).where(Show.screen_id == screen.id)):
        for s in recat:
            price = (show.prices or {}).get(s.category)
            if price is not None:
                db.execute(update(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == s.id).values(price_paise=int(price)))
        materialize_show_seats(db, show)
    return len(desired)


def screen_categories(db: Session, screen_id: int) -> list[str]:
    return list(db.scalars(select(Seat.category).where(Seat.screen_id == screen_id).distinct()))


def materialize_show_seats(db: Session, show: Show) -> int:
    """Create one ShowSeat per physical seat, priced per category. Single set-based INSERT..SELECT."""
    total = 0
    for category, price in (show.prices or {}).items():
        res = db.execute(
            text(
                "INSERT INTO show_seats (show_id, seat_id, category, price_paise, status) "
                "SELECT :show, id, category, :price, CASE WHEN is_blocked THEN 'blocked' ELSE 'available' END FROM seats "
                "WHERE screen_id = :screen AND category = :cat ON CONFLICT (show_id, seat_id) DO NOTHING"
            ),
            {"show": show.id, "price": int(price), "screen": show.screen_id, "cat": category},
        )
        total += res.rowcount or 0
    return total


def seat_map(db: Session, show_id: int, viewer_id: int | None) -> list[dict]:
    now = utcnow()
    rows = db.execute(
        select(ShowSeat, Seat).join(Seat, Seat.id == ShowSeat.seat_id).where(ShowSeat.show_id == show_id)
        .order_by(Seat.row_index, Seat.number)
    ).all()
    out = []
    for ss, seat in rows:
        status = ss.status
        if status == "locked" and (ss.locked_until is None or ss.locked_until <= now):
            status = "available"  # expired lock not swept yet
        mine = status == "locked" and ss.locked_by == viewer_id
        out.append(
            {
                "id": ss.id, "row": seat.row_label, "number": seat.number, "category": ss.category,
                "price_paise": ss.price_paise, "status": status, "mine": mine,
            }
        )
    return out


def set_locks(db: Session, user_id: int, show: Show, seat_ids: list[int]) -> tuple[datetime | None, list[dict]]:
    """Replace the caller's temporary holds on `show` with exactly `seat_ids`.

    Row locks are taken in id order in a single statement so concurrent callers can't deadlock.
    Returns (lock expiry, seat status changes to broadcast).
    """
    if len(set(seat_ids)) != len(seat_ids):
        raise AppError(400, "duplicate_seats", "Duplicate seats in request")
    if len(seat_ids) > settings.max_seats_per_booking:
        raise AppError(400, "too_many_seats", f"You can select up to {settings.max_seats_per_booking} seats")
    now = utcnow()
    if show.starts_at <= now or not show_is_public(db, show):
        raise AppError(409, "show_closed", "Booking is closed for this show")

    rows = list(
        db.scalars(
            select(ShowSeat)
            .where(
                ShowSeat.show_id == show.id,
                or_(
                    ShowSeat.id.in_(seat_ids) if seat_ids else False,
                    (ShowSeat.locked_by == user_id) & (ShowSeat.status == "locked") & ShowSeat.booking_id.is_(None),
                ),
            )
            .order_by(ShowSeat.id)
            .with_for_update()
        )
    )
    by_id = {r.id: r for r in rows}
    if any(i not in by_id for i in seat_ids):
        raise not_found("Seat")

    conflicts = []
    for i in seat_ids:
        r = by_id[i]
        taken = r.status in ("booked", "blocked") or (
            r.status == "locked" and r.locked_until and r.locked_until > now and r.locked_by != user_id
        )
        if taken:
            conflicts.append(i)
    if conflicts:
        raise conflict("Some seats were just taken by someone else", "seat_unavailable", {"seat_ids": conflicts})

    changes: list[dict] = []
    wanted = set(seat_ids)
    for r in rows:
        if r.id not in wanted and r.locked_by == user_id and r.status == "locked" and r.booking_id is None:
            r.status, r.locked_by, r.locked_until = "available", None, None
            changes.append({"id": r.id, "status": "available"})
    if seat_ids:
        elsewhere = db.scalar(
            select(func.count()).select_from(ShowSeat).where(
                ShowSeat.locked_by == user_id, ShowSeat.status == "locked", ShowSeat.locked_until > now,
                ShowSeat.show_id != show.id)
        )
        if elsewhere + len(seat_ids) > settings.max_seats_per_booking * 3:
            raise AppError(429, "too_many_holds", "You are holding too many seats across shows. Complete or release some first.")
    expiry = now + timedelta(minutes=settings.seat_lock_minutes) if seat_ids else None
    for i in seat_ids:
        r = by_id[i]
        was_mine = r.status == "locked" and r.locked_by == user_id
        r.status, r.locked_by, r.locked_until = "locked", user_id, expiry
        if not was_mine:
            changes.append({"id": r.id, "status": "locked"})
    return expiry, changes


def sweep_expired_locks(db: Session) -> dict[int, list[dict]]:
    """Free holds whose TTL passed (not attached to a pending booking). Returns changes grouped by show."""
    now = utcnow()
    rows = db.scalars(
        select(ShowSeat)
        .where(ShowSeat.status == "locked", ShowSeat.locked_until < now, ShowSeat.booking_id.is_(None))
        .with_for_update(skip_locked=True)
    ).all()
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        r.status, r.locked_by, r.locked_until = "available", None, None
        grouped.setdefault(r.show_id, []).append({"id": r.id, "status": "available"})
    return grouped


def publish_grouped(grouped: dict[int, list[dict]]) -> None:
    for show_id, seats in grouped.items():
        publish_seats(show_id, seats)
