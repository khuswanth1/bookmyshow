"""One-time codes for email verification and password reset.

Only an HMAC of the code is stored. Codes expire quickly, are single use, and are burned after too many wrong guesses.
"""
import hmac
import logging
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, bad_request
from app.core.security import hmac_sha256
from app.models import OtpCode
from app.services.notify import send_email
from app.services.seats import utcnow

log = logging.getLogger("otp")

TTL = timedelta(minutes=10)
RESEND_AFTER = timedelta(seconds=45)
MAX_ATTEMPTS = 5

SUBJECTS = {"verify_email": "Verify your email", "reset_password": "Reset your password"}


def _hash(email: str, purpose: str, code: str) -> str:
    return hmac_sha256(settings.jwt_secret, f"otp|{email}|{purpose}|{code}")


def dev_codes_visible() -> bool:
    """Codes are echoed in API responses only when no mail transport exists and we are not in production."""
    return not settings.is_prod and not settings.smtp_host


def issue(db: Session, email: str, purpose: str) -> str:
    """Create and send a new code. Returns the plain code (callers decide whether it may leave the server)."""
    email = email.lower()
    latest = db.scalar(select(OtpCode).where(OtpCode.email == email, OtpCode.purpose == purpose)
                       .order_by(OtpCode.id.desc()).limit(1))
    if latest and utcnow() - latest.created_at < RESEND_AFTER:
        raise AppError(429, "otp_too_soon", "Please wait a few seconds before requesting another code")
    for old in db.scalars(select(OtpCode).where(OtpCode.email == email, OtpCode.purpose == purpose,
                                                OtpCode.consumed_at.is_(None))):
        old.consumed_at = utcnow()
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(OtpCode(email=email, purpose=purpose, code_hash=_hash(email, purpose, code), expires_at=utcnow() + TTL))
    db.flush()
    send_email(email, f"{SUBJECTS[purpose]} - BookMyShow",
               f"Your code is {code}. It expires in {int(TTL.total_seconds() // 60)} minutes.\n"
               "If you did not request it, you can ignore this message.")
    return code


def check(db: Session, email: str, purpose: str, code: str) -> None:
    """Validate and consume a code, or raise. Wrong guesses are counted against the newest live code."""
    email = email.lower()
    row = db.scalar(select(OtpCode).where(OtpCode.email == email, OtpCode.purpose == purpose,
                                          OtpCode.consumed_at.is_(None)).order_by(OtpCode.id.desc())
                    .limit(1).with_for_update())
    if not row or row.expires_at < utcnow() or row.attempts >= MAX_ATTEMPTS:
        raise bad_request("That code is invalid or has expired. Request a new one.", "otp_invalid")
    if not hmac.compare_digest(row.code_hash, _hash(email, purpose, code)):
        row.attempts += 1
        db.commit()  # persist the failed attempt even though we raise
        raise bad_request("That code is incorrect.", "otp_invalid")
    row.consumed_at = utcnow()
