"""Write a Subject's weak subtasks as crop cards into the user's Notion database. Run by the worker; no LLM."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .. import anki
from ..core.crypto import decrypt, encrypt
from ..db.models import Course, Integration, NotionCard, NotionDatabase
from ..mcp import tools
from . import client
from .cards import build_card

EARLY = timedelta(minutes=5)  # refresh a token that expires sooner than this before the first call


class ExportFailed(Exception):
    """An end the user must act on; `.code` is the job's error_code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def lock_key(integration_id: uuid.UUID) -> int:
    return int.from_bytes(integration_id.bytes[:8], "big", signed=True)


class _Token:
    """The access token of one connection. A 401 refreshes it once per export; the next 401 ends the export."""

    def __init__(self, db: Session, integ: Integration):
        self.db, self.integ, self.refreshed = db, integ, False
        self.value = decrypt(integ.access_token)
        if integ.refresh_token and integ.expires_at and integ.expires_at - datetime.now(UTC) < EARLY:
            self._refresh()

    def _refresh(self) -> None:
        if self.refreshed or not self.integ.refresh_token:
            raise ExportFailed("notion_auth")
        self.refreshed = True
        try:
            t = client.refresh(decrypt(self.integ.refresh_token))
        except client.NotionError as e:
            if e.status in (400, 401):  # invalid_grant or revoked: only reconnecting helps
                raise ExportFailed("notion_auth") from None
            raise
        # stored before the retry: Notion rotates the refresh token, so the old one is dead now
        self.integ.access_token = encrypt(t["access_token"])
        if t["refresh_token"]:
            self.integ.refresh_token = encrypt(t["refresh_token"])
        self.integ.expires_at = datetime.now(UTC) + timedelta(seconds=t["expires_in"]) if t["expires_in"] else None
        self.db.commit()
        self.value = t["access_token"]

    def call(self, fn, *args):
        try:
            return fn(self.value, *args)
        except client.NotionAuth:
            self._refresh()
            return self.call(fn, *args)


def _database(db: Session, token: _Token, integration_id: uuid.UUID) -> NotionDatabase:
    store = db.scalar(select(NotionDatabase).where(NotionDatabase.integration_id == integration_id))
    if store is None:
        database_id, data_source_id, url = token.call(client.create_database)
        store = NotionDatabase(integration_id=integration_id, database_id=database_id, data_source_id=data_source_id, url=url)
        db.add(store)
        db.commit()
    return store


def _send(
    db: Session,
    token: _Token,
    integration_id: uuid.UUID,
    user_id: uuid.UUID,
    course: Course,
    refs: list[str],
    again: bool,
    on_card: Callable[[], None],
) -> int:
    """Pages created for the refs without a card; a deleted database is dropped and refilled once (`again`)."""
    store = _database(db, token, integration_id)
    sent = {(e, k) for e, k in db.execute(select(NotionCard.exam_id, NotionCard.subtask_key).where(NotionCard.integration_id == integration_id))}
    shares = tools.latest_shares(db, user_id, course.id)
    created = 0
    for ref in refs:
        exam, key = ref.split("/", 1)
        exam = uuid.UUID(exam)
        if (exam, key) in sent:
            continue
        q, q_paths = tools.get_task(db, user_id, ref, False)
        a, paths = tools.get_task(db, user_id, ref, True)  # the solution crops follow the question crops, as in anki.build_deck
        q_ids = [i for p in q_paths if (i := token.call(client.upload_image, p))]
        a_ids = [i for p in paths[len(q_paths) :] if (i := token.call(client.upload_image, p))]
        properties, children = build_card(q, a, shares[(exam, key)], course.name, q_ids, a_ids)
        try:
            # shortcut: a crash between Notion's answer and the commit, or the client's retry of a 5xx that Notion had
            # already applied, leaves one duplicate page; dedupe by a stored key property if users report doubles
            page_id = token.call(client.create_page, store.data_source_id, properties, children)
        except client.NotionGone:
            if not again:  # the new database is gone too: a retry would only create another one
                raise ExportFailed("server") from None
            db.execute(delete(NotionCard).where(NotionCard.integration_id == integration_id))
            db.execute(delete(NotionDatabase).where(NotionDatabase.integration_id == integration_id))
            db.commit()
            return _send(db, token, integration_id, user_id, course, refs, again=False, on_card=on_card)
        db.add(NotionCard(integration_id=integration_id, exam_id=exam, subtask_key=key, page_id=page_id))
        db.commit()  # one by one, so a retry after a crash skips what was sent
        created += 1
        on_card()
    return created


def export_subject(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, on_card: Callable[[], None] = lambda: None) -> int:
    """Creates a page for each weak subtask of the Subject that has none yet; returns how many it created.
    `on_card` runs after each card is committed (the worker's heartbeat)."""
    integ = db.scalar(select(Integration).where(Integration.user_id == user_id, Integration.provider == "notion"))
    if integ is None:
        raise ExportFailed("notion_not_connected")
    refs = tools.weak_refs(db, user_id, course_id, anki.BELOW, anki.LIMIT)  # [] for another user's course
    if not refs:
        raise ExportFailed("nothing_weak")
    course = db.get(Course, course_id)
    key = {"k": lock_key(integ.id)}
    # the Session gives its connection back on every commit, so the session-level lock lives on a connection of its own
    with db.get_bind().connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(:k)"), key)
        lock.commit()  # the lock outlives the transaction; don't sit idle in one for the whole export
        try:
            db.refresh(integ)  # another export may have refreshed the tokens while this one waited
            return _send(db, _Token(db, integ), integ.id, user_id, course, refs, again=True, on_card=on_card)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), key)
            lock.commit()
