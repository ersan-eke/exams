"""Postgres schema.

Columns hold what gets joined, filtered or summed (points, times, grades); JSONB holds what is
always read and written whole and whose shape the code owns (pipeline geometry, pen strokes).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # stable constraint names, so later migrations can drop/alter them by name
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {datetime: DateTime(timezone=True), Decimal: Numeric(6, 2)}  # noqa: RUF012 - SQLAlchemy's API


def choice(name: str, *values: str) -> Enum:
    """varchar + CHECK instead of a native ENUM: adding a value later is a plain migration, not ALTER TYPE."""
    return Enum(*values, name=name, native_enum=False, create_constraint=True, length=max(map(len, values)))


def created() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def updated() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None]  # not unique: identity comes from the OAuth provider id, never the email
    name: Mapped[str | None]
    created_at: Mapped[datetime] = created()


class OAuthAccount(Base):
    """A login identity at GitHub/Google. One user can have several; matched by the provider's id, never by email."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(choice("oauth_provider", "github", "google"))
    provider_user_id: Mapped[str]
    created_at: Mapped[datetime] = created()


class LoginSession(Base):
    """Server-side session behind the cookie: deleting the row logs that device out."""

    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie; a DB leak yields no live cookies
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = created()
    expires_at: Mapped[datetime]


class AccessToken(Base):
    """Personal access token (Bearer on /mcp): shown once on creation, only its hash is stored."""

    __tablename__ = "access_tokens"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = created()
    last_used_at: Mapped[datetime | None]


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (Index("ix_courses_user_lower_name", "user_id", text("lower(name)"), unique=True),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str]


class Chat(Base):
    """A conversation about one Subject. Messages (user texts and search turns) and pinned pages are read and written whole, so JSONB."""

    __tablename__ = "chats"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str]
    messages: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    pinned: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()


class Exam(Base):
    """One uploaded PDF's structure. Field names match pipeline.models.ExamStructure (see db/exams.py)."""

    __tablename__ = "exams"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # made by the client, so offline records keep their id
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    title: Mapped[str]
    has_ink: Mapped[bool] = mapped_column(default=False)
    hidden: Mapped[bool] = mapped_column(default=False)
    # pipeline output
    source: Mapped[str]
    page_count: Mapped[int]
    page_sizes: Mapped[list[Any]] = mapped_column(JSONB)
    kind: Mapped[str] = mapped_column(choice("exam_kind", "digital", "scanned", "mixed"))
    is_solution: Mapped[bool]
    total_points_stated: Mapped[Decimal | None]
    duration_minutes: Mapped[int | None]
    mc_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    issues: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    point_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rubrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    solution_for: Mapped[uuid.UUID | None]  # no FK: the exam it solves may not have synced yet
    fingerprint: Mapped[str | None]
    edited_at: Mapped[datetime] = mapped_column(server_default=text("to_timestamp(0)"))  # epoch until a client pushes, so a first push always applies
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()

    tasks: Mapped[list["Task"]] = relationship(cascade="all, delete-orphan", order_by="Task.position")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("exam_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)  # internal; the API speaks in `key`
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"))
    position: Mapped[int]
    key: Mapped[str]  # "A2"
    number: Mapped[str]
    title: Mapped[str]
    points: Mapped[Decimal | None]
    context: Mapped[list[Any]] = mapped_column(JSONB)  # rendered with the task, never queried
    mc_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # the task intro's MC rule

    subtasks: Mapped[list["Subtask"]] = relationship(cascade="all, delete-orphan", order_by="Subtask.position")


class Subtask(Base):
    __tablename__ = "subtasks"
    __table_args__ = (UniqueConstraint("task_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    position: Mapped[int]
    key: Mapped[str]  # "A2b"
    label: Mapped[str]
    points: Mapped[Decimal | None]
    independent: Mapped[bool]
    text: Mapped[str]
    solution_text: Mapped[str]
    # geometry: only ever drawn together, so one JSONB value each instead of child tables
    regions: Mapped[list[Any]] = mapped_column(JSONB)
    mc_options: Mapped[list[Any]] = mapped_column(JSONB)
    mc_key: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    answer_boxes: Mapped[list[Any]] = mapped_column(JSONB)


class Document(Base):
    """One uploaded study PDF (a chapter of slides, a script, tutorial exercises). course_id is NULL until it is assigned to a subject."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("user_id", "sha256"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(choice("document_kind", "slides", "script", "exercises"))
    title: Mapped[str]
    position: Mapped[int] = mapped_column(default=0)  # order of the chapters within a subject
    filename: Mapped[str]
    sha256: Mapped[str]
    page_count: Mapped[int] = mapped_column(default=0)
    outline: Mapped[list | None] = mapped_column(JSONB)  # two levels, see rag/outline.py; NULL until the Deck is read
    outline_source: Mapped[str | None]  # "automatic" or "ai"; NULL = not built yet
    created_at: Mapped[datetime] = created()


class DeckPage(Base):
    """What was read from one page of a Deck: the printed slide label, title, footer section, accent headings and the cleaned text.
    A Deck without rows here has not been read yet (the idle worker backfills it)."""

    __tablename__ = "deck_pages"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    page: Mapped[int] = mapped_column(primary_key=True)  # 1-based
    label: Mapped[str | None]  # e.g. "3-21"; overlay builds of one slide share it
    title: Mapped[str] = mapped_column(default="")
    section: Mapped[str] = mapped_column(default="")
    headings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    body: Mapped[str] = mapped_column(default="")


class Chunk(Base):
    """A searchable piece of text: one page of a document, or one subtask of an exam (exactly one of the two ids is set)."""

    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("(document_id IS NULL) <> (subtask_id IS NULL)", name="owner"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_embedding", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    subtask_id: Mapped[int | None] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"), index=True)
    page: Mapped[int | None]  # 1-based, documents only
    text: Mapped[str]
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True))
    embedding: Mapped[Any] = mapped_column(
        Vector(384)
    )  # shortcut: model fixed (paraphrase-multilingual-MiniLM-L12-v2), changing it needs a re-embed migration


class Job(Base):
    """One uploaded PDF waiting for / going through the pipeline. The table is also the queue (see worker)."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("uq_jobs_active_notion", "course_id", unique=True, postgresql_where=text("kind = 'notion' AND status IN ('queued','running')")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str]
    kind: Mapped[str] = mapped_column(choice("job_kind", "exam", "document", "notion"), default="exam", server_default="exam")
    role: Mapped[str | None] = mapped_column(choice("upload_role", "exam", "solution"))  # exam jobs only
    status: Mapped[str] = mapped_column(choice("job_status", "queued", "running", "done", "failed"), default="queued")
    stage: Mapped[str | None]  # extract | enrich | render | embed | export, while running
    attempts: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None]  # upload: scanned, no_tasks, unreadable, server; notion: nothing_weak, notion_not_connected, notion_auth
    exam_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exams.id", ondelete="SET NULL"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    subject: Mapped[str | None]  # the browser's guess; names the course the exam is filed under
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))  # notion jobs only
    locked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created()
    finished_at: Mapped[datetime | None]


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # made by the client
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    solution_exam_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exams.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(choice("attempt_status", "running", "handed_in"))
    fresh: Mapped[bool]
    started_at: Mapped[datetime]
    time_limit_ms: Mapped[int]
    included_task_ids: Mapped[list[str]] = mapped_column(ARRAY(String))
    attendance_at_ms: Mapped[int | None]  # ms after start
    attendance_done: Mapped[bool]
    mc_rule: Mapped[dict[str, Any]] = mapped_column(JSONB)
    extended: Mapped[bool]
    overtime: Mapped[bool] = mapped_column(server_default=text("false"))
    edited_at: Mapped[datetime] = created()
    handed_in_at: Mapped[datetime | None]
    graded_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = updated()  # sync cursor

    # read side only: app.db.attempts writes the children as rows
    answers: Mapped[list["Answer"]] = relationship(viewonly=True)
    times: Mapped[list["SubtaskTime"]] = relationship(viewonly=True)
    grades: Mapped[list["Grade"]] = relationship(viewonly=True)


class Answer(Base):
    """`main` = the answers frozen when time ran out (the old Attempt.snapshot), `over` = after extra time."""

    __tablename__ = "answers"
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True)
    subtask_id: Mapped[int] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[str] = mapped_column(choice("answer_version", "main", "over"), primary_key=True)
    mode: Mapped[str] = mapped_column(choice("answer_mode", "type", "draw"))
    parts: Mapped[list[Any]] = mapped_column(JSONB)  # text + strokes per answer box, written whole
    done: Mapped[bool]
    ticks: Mapped[list[int]] = mapped_column(ARRAY(Integer))


class SubtaskTime(Base):
    __tablename__ = "subtask_times"
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True)
    subtask_id: Mapped[int] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"), primary_key=True)
    main_ms: Mapped[int]
    over_ms: Mapped[int]


class Grade(Base):
    __tablename__ = "grades"
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True)
    subtask_id: Mapped[int] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"), primary_key=True)
    main: Mapped[Decimal | None]
    over: Mapped[Decimal | None]
    comment: Mapped[str | None]
    marks: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # grader pen strokes per version
    llm: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Integration(Base):
    """A user's connection to a third-party workspace (Slack, later Notion); the token is Fernet ciphertext."""

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("provider", "workspace_id", "external_user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(choice("integration_provider", "slack", "notion"))
    workspace_id: Mapped[str]
    workspace_name: Mapped[str]
    external_user_id: Mapped[str]
    access_token: Mapped[str]
    refresh_token: Mapped[str | None]  # Fernet ciphertext, like access_token
    scopes: Mapped[str]
    expires_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created()


class NotionDatabase(Base):
    """The Notion database the weak questions of one connection are exported into."""

    __tablename__ = "notion_databases"
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), primary_key=True)
    database_id: Mapped[str]
    data_source_id: Mapped[str]
    url: Mapped[str]


class NotionCard(Base):
    """The Notion page made for one subtask, so a re-export updates it instead of duplicating."""

    __tablename__ = "notion_cards"
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), primary_key=True)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True)
    subtask_key: Mapped[str] = mapped_column(primary_key=True)
    page_id: Mapped[str]


class WebhookEvent(Base):
    """Delivered webhook event ids: INSERT ... ON CONFLICT DO NOTHING tells a retry from a first delivery."""

    __tablename__ = "webhook_events"
    provider: Mapped[str] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(primary_key=True)
    received_at: Mapped[datetime] = created()
