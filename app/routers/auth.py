from fastapi import APIRouter, Depends
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token as g_id_token
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DB
from app.core.errors import AppError, bad_request, conflict, unauthorized
from app.core.security import (
    RateLimiter, create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.models import User, VendorStaff
from app.services import otp as otp_svc
from app.services.platform import audit
from app.schemas import (
    EmailVerifyIn, ForgotIn, GoogleIn, LoginIn, Msg, OtpSentOut, PasswordChange, RefreshIn, RegisterIn, ResetIn,
    TokenOut, UserOut, UserUpdate,
)

router = APIRouter(tags=["Auth"])
auth_limit = RateLimiter(20, 60, "auth")


def _tokens(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/auth/register", response_model=TokenOut, status_code=201, dependencies=[Depends(auth_limit)],
             summary="Create an account with email + password")
def register(body: RegisterIn, db: DB):
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise conflict("An account with this email already exists", "email_taken")
    user = User(email=email, name=body.name.strip(), phone=body.phone, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit(db, user, "auth.register", "user", user.id)
    db.commit()
    return _tokens(user)


@router.post("/auth/login", response_model=TokenOut, dependencies=[Depends(auth_limit)], summary="Email + password login")
def login(body: LoginIn, db: DB):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        audit(db, user, "auth.login_failed", "user", user.id if user else None, {"email": body.email[:120]}, actor_email=body.email[:120])
        db.commit()
        raise unauthorized("Incorrect email or password")
    if not user.is_active:
        if db.scalar(select(VendorStaff.id).where(VendorStaff.user_id == user.id, VendorStaff.status == "pending")):
            raise AppError(403, "staff_pending", "This staff account is waiting for admin approval")
        raise AppError(403, "account_disabled", "This account has been disabled")
    if user.role != "user":  # privileged logins are always logged
        audit(db, user, "auth.login", "user", user.id)
        db.commit()
    return _tokens(user)


@router.post("/auth/google", response_model=TokenOut, dependencies=[Depends(auth_limit)],
             summary="Sign in / sign up with a Google ID token")
def google_login(body: GoogleIn, db: DB):
    if not settings.google_client_id:
        raise AppError(503, "google_unavailable", "Google sign-in is not configured on this server")
    try:
        info = g_id_token.verify_oauth2_token(body.credential, g_requests.Request(), settings.google_client_id)
    except ValueError:
        raise unauthorized("Invalid Google credential")
    if not info.get("email_verified"):
        raise bad_request("Your Google email is not verified")
    email, sub = info["email"].lower(), info["sub"]
    user = db.scalar(select(User).where((User.google_sub == sub) | (func.lower(User.email) == email)))
    if user:
        if not user.is_active:
            raise AppError(403, "account_disabled", "This account has been disabled")
        user.google_sub = user.google_sub or sub
        user.avatar_url = user.avatar_url or info.get("picture")
        user.email_verified = True  # Google asserted email_verified above
    else:
        user = User(email=email, name=info.get("name") or email.split("@")[0], google_sub=sub,
                    avatar_url=info.get("picture"), email_verified=True)
        db.add(user)
    db.commit()
    return _tokens(user)


@router.post("/auth/refresh", response_model=TokenOut, summary="Exchange a refresh token for new tokens")
def refresh(body: RefreshIn, db: DB):
    data = decode_token(body.refresh_token, "refresh")
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise unauthorized("Account not found or disabled")
    return _tokens(user)


@router.get("/auth/config", summary="Public client configuration (Google client id, payments on/off)")
def public_config():
    return {
        "google_client_id": settings.google_client_id or None,
        "razorpay_key_id": settings.razorpay_key_id or None,
        "convenience_fee_pct": settings.convenience_fee_pct,
        "gst_pct": settings.gst_pct,
        "seat_lock_minutes": settings.seat_lock_minutes,
    }


@router.get("/users/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.patch("/users/me", response_model=UserOut)
def update_me(body: UserUpdate, user: CurrentUser, db: DB):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    return user


@router.post("/users/me/password", response_model=Msg, summary="Change (or set, for Google accounts) your password")
def change_password(body: PasswordChange, user: CurrentUser, db: DB):
    if user.password_hash and not verify_password(body.current_password or "", user.password_hash):
        raise bad_request("Current password is incorrect", "wrong_password")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return Msg(message="Password updated")


# ------------------------------------------------------------------ email verification & password reset (OTP)
def _sent(code: str, message: str) -> OtpSentOut:
    return OtpSentOut(message=message, dev_code=code if otp_svc.dev_codes_visible() else None)


@router.post("/users/me/email/send-code", response_model=OtpSentOut, dependencies=[Depends(auth_limit)],
             summary="Email a 6-digit code to verify your address")
def send_verification(user: CurrentUser, db: DB):
    if user.email_verified:
        raise conflict("Your email is already verified", "already_verified")
    code = otp_svc.issue(db, user.email, "verify_email")
    db.commit()
    return _sent(code, "We emailed you a verification code")


@router.post("/users/me/email/verify", response_model=UserOut, dependencies=[Depends(auth_limit)],
             summary="Confirm the emailed verification code")
def verify_email(body: EmailVerifyIn, user: CurrentUser, db: DB):
    otp_svc.check(db, user.email, "verify_email", body.code)
    user.email_verified = True
    audit(db, user, "auth.email_verified", "user", user.id)
    db.commit()
    return user


@router.post("/auth/password/forgot", response_model=OtpSentOut, dependencies=[Depends(auth_limit)],
             summary="Request a password-reset code (always answers the same, so emails cannot be enumerated)")
def forgot_password(body: ForgotIn, db: DB):
    email = body.email.lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active))
    code = None
    if user:
        try:
            code = otp_svc.issue(db, email, "reset_password")
            db.commit()
        except AppError:
            db.rollback()  # throttled: still answer generically
    return OtpSentOut(message="If that email has an account, a reset code is on its way.",
                      dev_code=code if (code and otp_svc.dev_codes_visible()) else None)


@router.post("/auth/password/reset", response_model=Msg, dependencies=[Depends(auth_limit)],
             summary="Set a new password using the emailed code")
def reset_password(body: ResetIn, db: DB):
    email = body.email.lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active))
    if not user:  # same error as a wrong code
        raise bad_request("That code is invalid or has expired. Request a new one.", "otp_invalid")
    otp_svc.check(db, email, "reset_password", body.code)
    user.password_hash = hash_password(body.new_password)
    user.email_verified = True  # proving control of the mailbox
    audit(db, user, "auth.password_reset", "user", user.id)
    db.commit()
    return Msg(message="Password updated. You can sign in now.")
