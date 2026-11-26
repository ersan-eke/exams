import uuid

from sqlalchemy import func, select
from test_db import SAMPLE

from app.db.exams import to_rows
from app.db.models import Chunk, Subtask, Task, User
from app.rag.index import index_pending


def test_index_pending_covers_new_subtasks_once_and_skips_anonymous_exams(db):
    u = uuid.uuid4()
    db.add(User(id=u))
    db.flush()
    mine, anon = uuid.uuid4(), uuid.uuid4()
    db.add_all([to_rows(mine, SAMPLE, title="Mine", user_id=u), to_rows(anon, SAMPLE, title="Anon")])
    db.commit()
    wanted = len([s for t in SAMPLE.tasks for s in t.subtasks if (s.text + s.solution_text).strip()])
    while index_pending(db, limit=1000):  # other tests may have left subtasks waiting too
        pass
    assert index_pending(db, limit=1000) == 0  # idempotent

    def chunks_of(exam):
        q = select(func.count()).select_from(Chunk).join(Subtask, Chunk.subtask_id == Subtask.id).join(Task, Subtask.task_id == Task.id)
        return db.scalar(q.where(Task.exam_id == exam))

    assert chunks_of(mine) == wanted > 0
    assert chunks_of(anon) == 0  # no account, nothing is stored for search
