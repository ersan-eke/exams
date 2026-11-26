from collections.abc import Callable

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine)


def get_db():
    with SessionLocal() as db:
        yield db


async def read_then_release[T](db: Session, read: Callable[..., T], *args) -> T:
    """For an async endpoint about to await something slow (an LLM call): runs `read(db, *args)` in the threadpool, then gives the
    connection back. Loaded objects (the request's `User` too) are detached, not expired, so reading them afterwards on the event
    loop runs no query; an attribute that was never loaded raises instead of quietly taking a connection again."""

    def run() -> T:
        try:
            return read(db, *args)
        finally:
            db.expunge_all()
            db.rollback()

    return await run_in_threadpool(run)
