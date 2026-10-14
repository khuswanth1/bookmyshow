from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import forbidden, unauthorized
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False, description="JWT access token from /auth/login")
DB = Annotated[Session, Depends(get_db)]


def _user_from(creds: HTTPAuthorizationCredentials | None, db: Session) -> User | None:
    if not creds:
        return None
    data = decode_token(creds.credentials, "access")
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise unauthorized("Account not found or disabled")
    return user


def current_user(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: DB) -> User:
    user = _user_from(creds, db)
    if not user:
        raise unauthorized()
    return user


def optional_user(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: DB) -> User | None:
    return _user_from(creds, db)


def require_roles(*roles: str):
    def dep(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise forbidden()
        return user

    return dep


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(require_roles("admin"))]
OrganizerUser = Annotated[User, Depends(require_roles("organizer", "admin"))]


class Page:
    def __init__(self, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
        self.page, self.size = page, size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


PageParams = Annotated[Page, Depends(Page)]


def paginate(db: Session, query, page: Page, scalars: bool = True):
    """Run `query` (a select) with a count and slice. Returns {items,total,page,size,pages}."""
    from sqlalchemy import func, select

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    q = query.limit(page.size).offset(page.offset)
    items = db.scalars(q).unique().all() if scalars else db.execute(q).all()
    return {"items": items, "total": total, "page": page.page, "size": page.size,
            "pages": max(1, -(-total // page.size))}
