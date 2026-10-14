"""Show scheduling shared by the admin panel and the vendor portal."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Movie, Screen, Show
from app.services import seats as seat_svc


def create_shows(db: Session, *, screen: Screen, movie: Movie, language_id: int, fmt: str, dates: list[date],
                 times: list[str], prices: dict[str, int], utc_offset_minutes: int, approval_status: str = "approved") -> dict:
    cats = set(seat_svc.screen_categories(db, screen.id))
    if not cats:
        raise AppError(400, "no_seats", "This screen has no seats")
    if set(prices) != cats:
        raise AppError(400, "prices_mismatch", f"Provide a price for exactly these categories: {sorted(cats)}")
    if any(p <= 0 for p in prices.values()):
        raise AppError(400, "invalid_price", "Prices must be positive")
    offset = timedelta(minutes=utc_offset_minutes)
    duration = timedelta(minutes=movie.duration_min + 15)
    created, skipped, ids = 0, [], []
    now = seat_svc.utcnow()
    for d in dates:
        for t in times:
            hh, mm = map(int, t.split(":"))
            start = datetime.combine(d, time(hh, mm), tzinfo=timezone.utc) - offset
            if start <= now:
                skipped.append({"date": str(d), "time": t, "reason": "in the past"})
                continue
            clash = db.scalar(select(Show.id).where(Show.screen_id == screen.id, Show.status == "active",
                                                   Show.starts_at < start + duration, Show.ends_at > start))
            if clash:
                skipped.append({"date": str(d), "time": t, "reason": "overlaps another show"})
                continue
            sh = Show(screen_id=screen.id, movie_id=movie.id, language_id=language_id, format=fmt, starts_at=start,
                      ends_at=start + duration, prices=prices, approval_status=approval_status)
            db.add(sh)
            db.flush()
            seat_svc.materialize_show_seats(db, sh)
            created += 1
            ids.append(sh.id)
    return {"created": created, "skipped": skipped, "show_ids": ids}
