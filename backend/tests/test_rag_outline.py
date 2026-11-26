import json
import logging
import uuid

import pytest
from pdf_util import L, make_pdf
from sqlalchemy import select
from test_auth import signed_in
from test_rag_ask import add_doc
from test_rag_slides import BLUE, slide

from app.db.models import Document
from app.db.session import engine
from app.grading.grader import ADAPTERS, Final
from app.grading.limits import ask_limiter
from app.rag import outline as rag_outline
from app.rag.deck import PageRead
from app.rag.index import backfill_decks
from app.rag.outline import BLOCK, build_outline

BODY = "ein langer Fliesstext unter dem Titel"  # longer than the title, so the body size is the usual one


def pages(*specs):
    """(title, section, mark) per page."""
    return [PageRead(i + 1, title=t, section=s, mark=m) for i, (t, s, m) in enumerate(specs)]


def shape(outline):
    return [(e["title"], e["page"], [(c["title"], c["page"]) for c in e["children"]]) for e in outline]


def test_bookmarks_give_two_levels_and_flatten_deeper_ones():
    out = build_outline(pages(("", "", (2, "Orphan")), ("", "", (1, "Ch 1")), ("", "", (2, "1.1")), ("", "", (3, "1.1.1")), ("x", "", (1, "Ch 2"))))
    assert shape(out) == [("Orphan", 1, []), ("Ch 1", 2, [("1.1", 3), ("1.1.1", 4)]), ("Ch 2", 5, [])]


def test_repeated_footer_sections_are_level_one_and_titles_level_two():
    out = build_outline(pages(("Intro", "A", None), ("Intro", "A", None), ("Mehr", "", None), ("Zwei", "B", None), ("", "B", None)))
    assert shape(out) == [("A", 1, [("Intro", 1), ("Mehr", 3)]), ("B", 4, [("Zwei", 4)])]


def test_a_footer_seen_once_is_not_structure():
    out = build_outline(pages(("T1", "only here", None), ("T2", "", None), ("T3", "", None)))
    assert shape(out) == [("Pages 1–3", 1, [("T1", 1), ("T2", 2), ("T3", 3)])]


def test_title_size_headings_merge_equal_consecutive_titles_in_blocks():
    out = build_outline(pages(("", "", None), ("A", "", None), ("A", "", None), ("", "", None), ("B", "", None), ("A", "", None)))
    assert shape(out) == [("Pages 1–6", 1, [("Page 1", 1), ("A", 2), ("B", 5), ("A", 6)])]


def test_no_structure_is_page_n_in_blocks():
    out = build_outline(pages(*[("", "", None)] * (BLOCK + 1)))
    assert [(e["title"], len(e["children"])) for e in out] == [(f"Pages 1–{BLOCK}", BLOCK), (f"Page {BLOCK + 1}", 1)]
    assert out[0]["children"][0] == {"title": "Page 1", "page": 1}


def upload(db, monkeypatch, pdf, name="d.pdf"):
    sub = f"outline-{uuid.uuid4()}"
    b = signed_in(monkeypatch, sub)
    add_doc(b, db, pdf, name, "Netze")
    return b, b.get("/api/documents", params={"subject": "Netze"}).json()[0]


def test_an_upload_stores_the_outline_with_its_source(db, monkeypatch):
    footer = make_pdf([slide("3-1", "Eins", BODY), slide("3-2", "Zwei", BODY), slide("3-3", "Drei", BODY)])
    _, d = upload(db, monkeypatch, footer)
    assert d["outline_source"] == "automatic"
    assert shape(d["outline"]) == [("Kapitel 3: Vermittlungsschicht", 1, [("Eins", 1), ("Zwei", 2), ("Drei", 3)])]

    marked = make_pdf([["a"], ["b"], ["c"]], outline=[("Teil 1", 1), ("Teil 2", 3)])
    _, d = upload(db, monkeypatch, marked)
    assert shape(d["outline"]) == [("Teil 1", 1, []), ("Teil 2", 3, [])]

    titles = make_pdf([[L("Eins", 24, BLUE, y=790), L(BODY, 12, y=700)], [L("Zwei", 24, BLUE, y=790), L(BODY, 12, y=700)]])
    _, d = upload(db, monkeypatch, titles)
    assert shape(d["outline"]) == [("Pages 1–2", 1, [("Eins", 1), ("Zwei", 2)])]

    _, d = upload(db, monkeypatch, make_pdf([["nur Text eins"], ["nur Text zwei"]]))
    assert shape(d["outline"]) == [("Pages 1–2", 1, [("Page 1", 1), ("Page 2", 2)])]


def test_existing_decks_get_an_outline_from_the_idle_worker(db, monkeypatch):
    b, d = upload(db, monkeypatch, make_pdf([["a text"], ["b text"]]))
    doc = db.get(Document, uuid.UUID(d["id"]))
    doc.outline = doc.outline_source = None  # a Deck from before Outlines
    db.commit()
    assert b.get(f"/api/documents/{d['id']}").json()["outline"] is None
    while backfill_decks(db):
        pass
    got = b.get(f"/api/documents/{d['id']}").json()
    assert got["outline_source"] == "automatic" and got["outline"]
    assert db.scalar(select(Document.outline_source).where(Document.id == doc.id)) == "automatic"


@pytest.fixture
def outline_llm():
    seen = {}
    orig = ADAPTERS["anthropic"]

    async def fake(req, key, system, items, out=None):
        seen.update(key=key, prompt=items[0].text, checked_out=engine.pool.checkedout())
        yield Final(
            json.dumps(
                seen.get("reply")
                or {
                    "sections": [
                        {"title": "Teil A", "page": 1, "children": [{"title": "Start", "page": 1}, {"title": "Ghost", "page": 99}]},
                        {"title": " ", "page": 2, "children": []},
                    ]
                }
            )
        )

    ADAPTERS["anthropic"] = fake
    ask_limiter.hits.clear()
    yield seen
    ADAPTERS["anthropic"] = orig


def test_ai_outline_sends_titles_and_openings_replaces_and_resets(db, monkeypatch, outline_llm, caplog):
    monkeypatch.setattr(rag_outline, "SNIPPET", 20)  # the test PDF cannot hold 200 characters on one line
    long_text = "x" * 500
    pdf = make_pdf([[L("Eins", 24, BLUE, y=790), L(long_text, 12, y=700)], [L("Zwei", 24, BLUE, y=790), L(BODY, 12, y=700)]])
    b, d = upload(db, monkeypatch, pdf)
    url = f"/api/documents/{d['id']}/outline"
    assert b.post(f"{url}/ai", json={}).json()["detail"] == {"code": "no_key"}

    with caplog.at_level(logging.DEBUG):
        r = b.post(f"{url}/ai", json={}, headers={"X-LLM-Key": "sk-secret-key"})
    assert r.status_code == 200, r.text
    assert outline_llm["key"] == "sk-secret-key" and "sk-secret-key" not in caplog.text
    first = outline_llm["prompt"].splitlines()[0]
    assert first.startswith("1 | Eins | ") and len(first.split(" | ")[2]) == 20  # title and the first SNIPPET characters of the body
    assert r.json()["outline_source"] == "ai"
    assert shape(r.json()["outline"]) == [("Teil A", 1, [("Start", 1)])]  # blank title and page 99 dropped
    assert b.get(f"/api/documents/{d['id']}").json()["outline_source"] == "ai"

    r = b.post(f"{url}/reset")
    assert r.json()["outline_source"] == "automatic"
    assert shape(r.json()["outline"]) == [("Pages 1–2", 1, [("Eins", 1), ("Zwei", 2)])]


def test_ai_outline_holds_no_db_connection_while_the_llm_answers(db, monkeypatch, outline_llm):
    b, d = upload(db, monkeypatch, make_pdf([["a text"], ["b text"]]))
    idle = engine.pool.checkedout()  # the test's own session may hold one
    r = b.post(f"/api/documents/{d['id']}/outline/ai", json={}, headers={"X-LLM-Key": "k"})
    assert r.status_code == 200, r.text
    assert outline_llm["checked_out"] == idle


def test_ai_outline_errors_and_ownership(db, monkeypatch, outline_llm):
    b, d = upload(db, monkeypatch, make_pdf([["a text"], ["b text"]]))
    url = f"/api/documents/{d['id']}/outline"
    outline_llm["reply"] = {"sections": []}
    assert b.post(f"{url}/ai", json={}, headers={"X-LLM-Key": "k"}).json()["detail"] == {"code": "llm_failed"}
    assert b.get(f"/api/documents/{d['id']}").json()["outline_source"] == "automatic"  # nothing replaced
    other = signed_in(monkeypatch, f"outline-{uuid.uuid4()}")
    assert other.post(f"{url}/ai", json={}, headers={"X-LLM-Key": "k"}).status_code == 404
    assert other.post(f"{url}/reset").status_code == 404


def test_ai_outline_keeps_one_entry_per_page_and_caps_titles():
    e = rag_outline.AiEntry
    out = rag_outline.AiOutline(
        sections=[
            rag_outline.AiSection(title="Zwei", page=3, children=[e(title="x" * 300, page=4)]),
            rag_outline.AiSection(title="Eins", page=1, children=[]),
            rag_outline.AiSection(title="Doppelt", page=3, children=[]),
        ]
    )
    got = rag_outline.from_ai(out, 5)
    assert [(s["title"], s["page"]) for s in got] == [("Eins", 1), ("Zwei", 3)]
    assert len(got[1]["children"][0]["title"]) == rag_outline.MAX_TITLE
