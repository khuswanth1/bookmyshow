import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.errors import install_error_handlers
from app.db.session import SessionLocal, engine
from app.routers import (
    admin, admin_platform, auth, bookings, calendar, catalog, checkin, commerce, events, helpdesk, organizer, shows, user_features,
    vendor, vendor_staff,
)
from app.schemas import ErrorOut
from app.services import booking as booking_svc
from app.services import seats as seat_svc
from app.services.platform import client_ip
from app.services.realtime import hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

DESCRIPTION = """
Full-stack **BookMyShow-style** ticketing API: movies, seat-level booking with live availability, events / plays /
sports / activities, a Stream catalog, Razorpay payments, organizer portal and admin panel.

**Auth**: `POST /api/v1/auth/login` → use the `access_token` as `Authorization: Bearer <token>` (click *Authorize*).
**Realtime**: `WS /api/v1/ws/shows/{show_id}` (public seat updates) and `WS /api/v1/ws/me?token=…` (private booking events).
Errors always look like `{"error": {"code", "message", "details"}}`.
"""

TAGS = [
    {"name": "Auth", "description": "Email/password, Google sign-in, JWT refresh, profile."},
    {"name": "Catalog", "description": "Cities, genres, languages, movies, cinemas, showtimes, search."},
    {"name": "Shows & Seats", "description": "Seat map, temporary seat locks, realtime WebSocket."},
    {"name": "Events, Plays, Sports & Activities", "description": "Non-movie ticketing with ticket-type inventory."},
    {"name": "Bookings & Payments", "description": "Checkout, Razorpay verification & webhook, cancellation, history."},
    {"name": "Offers & Gift Cards", "description": "Coupons (general / bank / corporate) and gift cards."},
    {"name": "User features, Stream & Support", "description": "Stream catalog, watchlist, favorites, notifications, support."},
    {"name": "Organizer Portal (ListYourShow)", "description": "Organizer onboarding, venues, events, inventory, analytics."},
    {"name": "Theater Vendor Portal", "description": "Vendor registration, theaters, screens, seat layouts, shows, bookings, earnings and payouts (own data only)."},
    {"name": "Admin Panel", "description": "Administrative management and reporting (admin role)."},
    {"name": "Super Admin: Marketplace", "description": "Vendor/theater/show approvals, commissions, payouts, platform settings, audit logs."},
]


async def housekeeping() -> None:
    """Every few seconds free expired seat holds and unpaid bookings, and tell connected clients."""
    def work():
        with SessionLocal() as db:
            grouped = seat_svc.sweep_expired_locks(db)
            n = booking_svc.expire_pending_bookings(db)
            booking_svc.commit(db)
            return grouped, n

    while True:
        await asyncio.sleep(10)
        try:
            grouped, n = await run_in_threadpool(work)
            seat_svc.publish_grouped(grouped)
        except Exception:
            log.exception("housekeeping failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    hub.loop = asyncio.get_running_loop()
    if not settings.razorpay_enabled:
        log.warning("Razorpay keys not set: checkout is disabled")
    task = asyncio.create_task(housekeeping()) if settings.env != "test" else None
    yield
    if task:
        task.cancel()
    engine.dispose()


app = FastAPI(
    title="BookMyShow Clone API", version="1.0.0", description=DESCRIPTION, openapi_tags=TAGS, lifespan=lifespan,
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json",
    responses={400: {"model": ErrorOut}, 401: {"model": ErrorOut}, 403: {"model": ErrorOut}, 404: {"model": ErrorOut},
               409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
install_error_handlers(app)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    client_ip.set(request.client.host if request.client else None)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if settings.is_prod:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return resp


PREFIX = "/api/v1"
for r in (auth, catalog, shows, events, bookings, commerce, user_features, organizer, vendor, admin, admin_platform,
          checkin, helpdesk, calendar, vendor_staff):
    app.include_router(r.router, prefix=PREFIX)
app.include_router(helpdesk.customer_router, prefix=PREFIX)
app.include_router(vendor_staff.admin_router, prefix=PREFIX)


@app.get("/health", tags=["Health"], summary="Liveness + database check")
def health():
    with engine.connect() as c:
        c.execute(text("select 1"))
    return {"status": "ok", "payments": settings.razorpay_enabled, "google": bool(settings.google_client_id)}
