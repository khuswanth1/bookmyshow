from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(Session, "do_orm_execute")
def _refresh_locked_rows(state):
    """`SELECT ... FOR UPDATE` must overwrite stale copies already in the identity map.

    Without this, a row loaded earlier in the request keeps its old column values even though the database
    returned the fresh, locked version -- which would silently defeat every lock-then-check in the booking engine.
    """
    if state.is_select and getattr(state.statement, "_for_update_arg", None) is not None:
        state.update_execution_options(populate_existing=True)
