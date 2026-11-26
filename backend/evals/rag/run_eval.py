"""Does Search put the right slide first? Run from backend/ against the dev database:

    uv run python -m evals.rag.run_eval --subject GRNVS

Each case in cases.json lists the printed slide labels that answer the question; hit@1 / hit@5 count a case when one of them is the
first / among the first five results. Local only: no key, no LLM."""

import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import Course
from app.db.session import SessionLocal
from app.rag.slides import search_slides


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    args = ap.parse_args()
    cases = json.loads((Path(__file__).parent / "cases.json").read_text())
    with SessionLocal() as db:
        courses = db.scalars(select(Course).where(func.lower(Course.name) == args.subject.strip().lower())).all()
        if len(courses) != 1:
            raise SystemExit(f"{len(courses)} Subjects called {args.subject!r}")
        course = courses[0]
        at1 = at5 = 0
        for c in cases:
            labels = [h.label for h in search_slides(db, course.user_id, course.id, [c["question"]])]
            rank = next((i + 1 for i, lab in enumerate(labels) if lab in c["expect"]), None)
            at1 += rank == 1
            at5 += rank is not None
            print(f"{'ok  ' if rank == 1 else 'top5' if rank else 'MISS'} {rank or '-':>1}  {c['question']}  expect {c['expect']}  got {labels}")
    print(f"hit@1 {at1}/{len(cases)}   hit@5 {at5}/{len(cases)}")


if __name__ == "__main__":
    main()
