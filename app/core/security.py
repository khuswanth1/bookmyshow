import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Request

from app.core.config import settings
from app.core.errors import AppError


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _token(sub: int, typ: str, ttl: timedelta, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(sub), "typ": typ, "iat": now, "exp": now + ttl, "jti": secrets.token_hex(8), **(extra or {})}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    return _token(user_id, "access", timedelta(minutes=settings.access_token_minutes), {"role": role})


def create_refresh_token(user_id: int) -> str:
    return _token(user_id, "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_typ: str) -> dict:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise AppError(401, "token_expired", "Session expired, please sign in again")
    except jwt.PyJWTError:
        raise AppError(401, "invalid_token", "Invalid authentication token")
    if data.get("typ") != expected_typ:
        raise AppError(401, "invalid_token", "Invalid authentication token")
    return data


def hmac_sha256(key: str, msg: str | bytes) -> str:
    if isinstance(msg, str):
        msg = msg.encode()
    return hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()


def safe_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class RateLimiter:
    """Small in-process sliding-window limiter. Use Redis/an API gateway when running multiple workers."""

    def __init__(self, limit: int, window_s: int, name: str):
        self.limit, self.window, self.name = limit, window_s, name
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        if settings.env == "test":
            return
        key = f"{self.name}:{request.client.host if request.client else 'x'}"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise AppError(429, "rate_limited", "Too many attempts, please try again shortly")
        q.append(now)
