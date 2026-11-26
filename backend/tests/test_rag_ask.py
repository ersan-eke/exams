import uuid

import pytest
from pdf_util import make_pdf
from sqlalchemy import select
from test_auth import signed_in
from test_db import SAMPLE

from app.db.exams import course_id, to_rows
from app.db.models import Exam, User
from app.rag.index import index_pending
from app.rag.search import find_course, search
from app.worker.main import run_once

HERMITE = make_pdf(
    [["Gauss quadrature nodes are roots of Legendre polynomials"], ["Hermite interpolation matches values and derivatives at the nodes"]]
)
SPLINE = make_pdf([["Cubic splines are piecewise polynomials with continuous second derivatives"]])
QUESTION = "Hermite interpolation matches derivatives"


def user_of(db, sub):
    return db.scalar(select(User).where(User.email == f"{sub}@example.com")).id


def add_doc(browser, db, pdf, name, subject):
    browser.post("/api/documents", files={"file": (name, pdf, "application/pdf")}, data={"subject": subject})
    assert run_once(db)


def exam_with(question: str):
    t = SAMPLE.tasks[0]
    sub = t.subtasks[0].model_copy(update={"text": question, "solution_text": ""})
    return SAMPLE.model_copy(update={"is_solution": False, "tasks": [t.model_copy(update={"subtasks": [sub]})]})


@pytest.fixture
def material(db, monkeypatch):
    sub = f"rag-{uuid.uuid4()}"  # a new account per test: the database outlives a test, and an identical file would be deduplicated
    b = signed_in(monkeypatch, sub)
    uid = user_of(db, sub)
    add_doc(b, db, HERMITE, "chapter3.pdf", "Numerik")
    add_doc(b, db, SPLINE, "chapter4.pdf", "Numerik")
    add_doc(b, db, SPLINE.replace(b"Cubic", b"Cubix"), "other.pdf", "Algebra")  # another subject, near-identical text
    db.add(
        to_rows(
            uuid.uuid4(),
            exam_with("Explain Hermite interpolation of derivatives"),
            title="Endterm 2024",
            user_id=uid,
            course_id=course_id(db, uid, "Numerik"),
        )
    )
    db.commit()
    while index_pending(db):
        pass
    return b, uid


def test_search_finds_the_right_page_and_stays_in_the_subject(db, material):
    _, uid = material
    hits = search(db, uid, find_course(db, uid, "Numerik"), [QUESTION], k=5)
    assert hits[0].page == 2 and hits[0].title == "chapter3" and hits[0].sim > 0.3
    assert all(h.title != "other" for h in hits)  # the Algebra deck never shows up in Numerik
    docs_only = search(db, uid, find_course(db, uid, "Numerik"), [QUESTION], documents_only=True)
    assert all(h.document_id for h in docs_only)
    assert any(h.exam_id and h.subtask_key for h in hits)  # the exam task is searchable too


def test_search_never_crosses_accounts(db, material, monkeypatch):
    _, uid = material
    sub = f"rag-{uuid.uuid4()}"
    signed_in(monkeypatch, sub)
    other = user_of(db, sub)
    assert find_course(db, other, "Numerik") is None
    assert search(db, other, find_course(db, uid, "Numerik"), [QUESTION]) == []  # even holding the other course id


def test_lookup_returns_distinct_pages_and_nothing_for_unrelated_text(db, material):
    b, _ = material
    r = b.post("/api/materials/lookup", json={"subject": "numerik", "text": QUESTION, "solution_text": "derivatives at the nodes"})
    assert r.status_code == 200
    links = r.json()
    assert links[0]["title"] == "chapter3" and links[0]["page"] == 2 and len(links) <= 2
    assert len({(x["document_id"], x["page"]) for x in links}) == len(links)
    assert b.post("/api/materials/lookup", json={"subject": "numerik", "text": "zzz qqq xxx"}).json() == []
    assert b.post("/api/materials/lookup", json={"subject": "Unknown", "text": QUESTION}).json() == []


def test_lookup_needs_sign_in():
    from fastapi.testclient import TestClient

    from main import app

    assert TestClient(app).post("/api/materials/lookup", json={"subject": "x", "text": "y"}).status_code == 401


def test_find_tasks_matches_by_meaning_not_only_by_substring(db, material):
    from app.mcp import tools

    _, uid = material
    found = tools.find_tasks(db, uid, "Numerik", "derivatives Hermite", None)  # not a substring of the task text
    assert [f["preview"] for f in found] == ["Explain Hermite interpolation of derivatives"]
    assert tools.find_tasks(db, uid, "Numerik", "zzz qqq", None) == []


def test_material_block_is_small_labelled_and_only_for_the_signed_in_owner(db, material):
    from app.api.auth import COOKIE
    from app.rag.material import MAX_CHARS, material_for

    b, _ = material
    cookie = b.cookies.get(COOKIE)
    block = material_for(cookie, "Numerik", QUESTION)
    assert "[chapter3, p. 2]" in block and len(block) <= MAX_CHARS + 100
    assert material_for(None, "Numerik", QUESTION) == ""  # signed out
    assert material_for(cookie, "Algebra", QUESTION) == "" or "chapter3" not in material_for(cookie, "Algebra", QUESTION)
    assert material_for(cookie, "Unknown subject", QUESTION) == ""


def test_prompt_gets_material_only_without_a_solution():
    from app.grading.models import GradeIn
    from app.grading.prompt import Text, build_content

    base = {"points": 3, "question": {"text": "q"}, "answer": {"text": "a"}, "material": "[c, p. 1]\nslide text"}
    own = build_content(GradeIn.model_validate(base))
    assert any(isinstance(i, Text) and "slide text" in i.text for i in own)
    with_solution = build_content(GradeIn.model_validate({**base, "solution": {"text": "s"}}))
    assert not any(isinstance(i, Text) and "slide text" in i.text for i in with_solution)


def test_material_leaves_out_the_graded_and_the_solution_exam(db, material):
    from app.api.auth import COOKIE
    from app.grading.models import GradeIn
    from app.rag.material import material_for

    b, uid = material
    cookie = b.cookies.get(COOKIE)
    exam_id = db.scalar(select(Exam.id).where(Exam.user_id == uid))
    question = "Explain Hermite interpolation of derivatives"
    assert "Endterm 2024" in material_for(cookie, "Numerik", question)
    block = material_for(cookie, "Numerik", question, [exam_id])
    assert "Endterm 2024" not in block and "[chapter3, p. 2]" in block
    assert "Endterm 2024" in material_for(cookie, "Numerik", question, [uuid.uuid4()])  # unknown id: as before
    sol = uuid.uuid4()
    db.add(to_rows(sol, exam_with(question), title="Solution 2024", user_id=uid, course_id=course_id(db, uid, "Numerik")))
    db.commit()
    while index_pending(db):
        pass
    assert "Solution 2024" in material_for(cookie, "Numerik", question, [exam_id])
    both = material_for(cookie, "Numerik", question, [exam_id, sol])
    assert "Solution 2024" not in both and "Endterm 2024" not in both and "[chapter3, p. 2]" in both
    body = {"points": 1, "question": {"text": "q"}, "answer": {"text": "a"}}
    with pytest.raises(ValueError):
        GradeIn.model_validate({**body, "exclude_exams": ["nope"]})
