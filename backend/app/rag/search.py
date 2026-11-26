"""Hybrid retrieval: pgvector cosine + Postgres full-text, merged with Reciprocal Rank Fusion.

Every query is scoped to one user and one subject (course), so nothing ever crosses subjects or accounts."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..db.models import Chunk, Document, Exam, Subtask, Task
from . import embed

MIN_SIM = 0.3  # shortcut: picked by eye on two sample decks; tune with real slides if links come up empty or off-topic
POOL = 20  # candidates taken from each ranking before the merge
RRF_K = 60
# shortcut: pgvector's HNSW filters after the index scan, so a very large corpus can return fewer than POOL rows;
# turn on `hnsw.iterative_scan` (pgvector 0.8) if that ever shows.


@dataclass
class Hit:
    chunk_id: int
    text: str
    page: int | None  # documents only
    document_id: uuid.UUID | None
    exam_id: uuid.UUID | None
    title: str  # the chapter or the exam
    subtask_key: str | None
    sim: float = 0.0  # best cosine similarity to any query (0 when only the keyword search found it)
    score: float = 0.0  # RRF


def find_course(db: Session, user_id: uuid.UUID, name: str) -> uuid.UUID | None:
    from ..db.models import Course

    return db.scalar(select(Course.id).where(Course.user_id == user_id, func.lower(Course.name) == name.strip().lower()))


def similar_subtasks(db: Session, user_id: uuid.UUID, course: uuid.UUID, query: str, limit: int = 40) -> list[int]:
    """Ids of the course's exam subtasks that read like `query`, closest first (only those past MIN_SIM)."""
    if not query.strip():
        return []
    dist = Chunk.embedding.cosine_distance(embed.embed([query.strip()])[0])
    q = (
        select(Chunk.subtask_id)
        .join(Subtask, Chunk.subtask_id == Subtask.id)
        .join(Task, Subtask.task_id == Task.id)
        .join(Exam, Task.exam_id == Exam.id)
        .where(Exam.user_id == user_id, Exam.course_id == course, 1 - dist >= MIN_SIM)
        .order_by(dist)
        .limit(limit)
    )
    return list(db.scalars(q))


def _keywords(query: str) -> str:
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2][:30]
    return " | ".join(dict.fromkeys(words))  # \w+ only, so the tsquery syntax cannot be injected


def search(
    db: Session,
    user_id: uuid.UUID,
    course: uuid.UUID,
    queries: list[str],
    *,
    documents_only: bool = False,
    exams_only: bool = False,
    exclude_exams: Sequence[uuid.UUID] = (),
    k: int = 5,
) -> list[Hit]:
    queries = [q.strip() for q in queries if q.strip()]
    if not queries:
        return []
    scope = and_(Document.user_id == user_id, Document.course_id == course)
    if not documents_only:
        exams = and_(Exam.user_id == user_id, Exam.course_id == course, Exam.hidden.is_(False))
        if exclude_exams:
            exams = and_(exams, Exam.id.not_in(exclude_exams))
        scope = exams if exams_only else or_(scope, exams)
    cols = (Chunk.id, Chunk.text, Chunk.page, Document.id, Exam.id, func.coalesce(Document.title, Exam.title), Subtask.key)
    base = (
        select(*cols)
        .select_from(Chunk)
        .outerjoin(Document, Chunk.document_id == Document.id)
        .outerjoin(Subtask, Chunk.subtask_id == Subtask.id)
        .outerjoin(Task, Subtask.task_id == Task.id)
        .outerjoin(Exam, Task.exam_id == Exam.id)
        .where(scope)
    )
    rankings: list[list[tuple]] = []
    best_sim: dict[int, float] = {}
    for q, vec in zip(queries, embed.embed(queries), strict=True):
        dist = Chunk.embedding.cosine_distance(vec)
        rows = db.execute(base.add_columns((1 - dist).label("sim")).order_by(dist).limit(POOL)).all()
        for r in rows:
            best_sim[r[0]] = max(best_sim.get(r[0], 0.0), float(r[-1]))
        rankings.append([r[:-1] for r in rows])
        if tsq := _keywords(q):
            query = func.to_tsquery("simple", tsq)
            rankings.append(db.execute(base.where(Chunk.tsv.op("@@")(query)).order_by(func.ts_rank_cd(Chunk.tsv, query).desc()).limit(POOL)).all())
    rows_by_id: dict[int, tuple] = {}
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, row in enumerate(ranking):
            rows_by_id[row[0]] = row
            score[row[0]] = score.get(row[0], 0.0) + 1 / (RRF_K + rank + 1)
    top = sorted(score, key=score.__getitem__, reverse=True)[:k]
    return [Hit(*rows_by_id[i], sim=best_sim.get(i, 0.0), score=score[i]) for i in top]
