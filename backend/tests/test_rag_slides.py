import uuid
from collections import Counter

import pytest
from pdf_util import L, make_pdf
from sqlalchemy import delete, select
from test_auth import signed_in
from test_rag_ask import add_doc, exam_with, user_of

from app.db.exams import course_id, to_rows
from app.db.models import DeckPage, Document
from app.rag.index import backfill_decks, index_pending
from app.rag.search import find_course
from app.rag.slides import search_slides

BLUE = (0, 0.4, 0.74)


def slide(label, title, *body, heading=None):
    lines = [L(title, 24, BLUE, y=790), L(f"Kapitel 3: Vermittlungsschicht {label}", 6, y=15)]
    lines += [L(heading, 12, BLUE, y=720)] if heading else []
    lines += [L(b, 12, y=680 - 20 * i) for i, b in enumerate(body)]
    return lines


FILLER = "wie ist wie ist wie ist"
DECK = make_pdf(
    [
        slide("3-1", "Agenda", FILLER, "Kollisionsdomaenen Count-to-Infinity Sonstiges"),
        slide("3-2", "Kollisionsdomaenen", FILLER, "Eine Kollisionsdomaene ist ein Bereich", heading="Domaene Begriff"),
        slide("3-2", "Kollisionsdomaenen", FILLER, "Eine Kollisionsdomaene ist ein Bereich", "Hubs vergroessern sie"),  # a build of the same slide
        slide("3-3", "Count-to-Infinity", FILLER, "Routing Schleifen"),
        slide("3-4", "Sonstiges", FILLER, "nur im Fliesstext steht qqword"),
        slide("3-5", "Adressierung", FILLER, "Adressen im Internet"),
    ]
)
SCRIPT = make_pdf([["Das Skript erklaert Hamming Codes ausfuehrlich"], ["Weitere Seiten ohne Struktur"]])
OTHER = make_pdf([slide("1-1", "Kollisionsdomaenen", FILLER, "Gehoert zu einem anderen Fach")] * 3)


@pytest.fixture
def subject(db, monkeypatch):
    sub = f"rag-{uuid.uuid4()}"
    b = signed_in(monkeypatch, sub)
    uid = user_of(db, sub)
    add_doc(b, db, DECK, "kap3.pdf", "Netze")
    add_doc(b, db, SCRIPT, "skript.pdf", "Netze")
    add_doc(b, db, OTHER, "other.pdf", "Algebra")
    db.add(
        to_rows(
            uuid.uuid4(), exam_with("Erklaere Kollisionsdomaenen und Hubs"), title="Klausur 2024", user_id=uid, course_id=course_id(db, uid, "Netze")
        )
    )
    db.commit()
    while index_pending(db):
        pass
    return b, uid, find_course(db, uid, "Netze")


def labels(db, uid, course, q, **kw):
    return [(h.label, h.title) for h in search_slides(db, uid, course, [q], **kw)]


def test_upload_stores_the_page_structure(db, subject):
    _, uid, _ = subject
    doc = db.scalar(select(Document).where(Document.user_id == uid, Document.filename == "kap3.pdf"))
    p = {r.page: r for r in db.scalars(select(DeckPage).where(DeckPage.document_id == doc.id))}
    assert (p[2].label, p[2].title, p[2].section, p[2].headings) == (
        "3-2",
        "Kollisionsdomaenen",
        "Kapitel 3: Vermittlungsschicht",
        ["Domaene Begriff"],
    )
    assert len(p) == doc.page_count == 6


def test_a_deck_without_structure_is_searched_by_its_plain_text(db, subject):
    _, uid, course = subject
    hits = search_slides(db, uid, course, ["Hamming Codes"])
    assert hits[0].deck == "skript" and hits[0].label is None and hits[0].page == 1


def test_one_result_per_label_best_five_at_most_and_the_fullest_build(db, subject):
    _, uid, course = subject
    hits = search_slides(db, uid, course, ["Kollisionsdomaenen Hubs Count Routing Adressierung Hamming Sonstiges"])
    keys = [(h.document_id, h.label or h.page) for h in hits]
    assert len(hits) <= 5 and len(set(keys)) == len(keys)
    hit = next(h for h in search_slides(db, uid, course, ["Kollisionsdomaenen"]) if h.label == "3-2")
    assert hit.page == 3  # the second build has the extra line


def test_filler_words_do_not_drive_the_ranking(db, subject):
    _, uid, course = subject
    assert labels(db, uid, course, "wie ist Kollisionsdomaenen")[0] == ("3-2", "Kollisionsdomaenen")


def test_inflected_hyphenated_and_umlaut_forms_find_the_title(db, subject):
    _, uid, course = subject
    for q in ("Kollisionsdomänen", "kollisions-domaene", "wie bestimme ich Kollisionsdomaenen?"):
        assert labels(db, uid, course, q)[0] == ("3-2", "Kollisionsdomaenen"), q
    for q in ("count to infinity", "Count-to-Infinity", "counttoinfinity"):
        assert labels(db, uid, course, q)[0] == ("3-3", "Count-to-Infinity"), q


def test_agenda_pages_do_not_outrank_the_slide_that_explains_the_topic(db, subject):
    _, uid, course = subject
    assert labels(db, uid, course, "Count-to-Infinity")[0][0] == "3-3"  # the agenda page names it too


def test_weak_results_are_flagged_not_hidden(db, subject):
    _, uid, course = subject
    strong = search_slides(db, uid, course, ["Kollisionsdomaenen"])[0]
    weak = search_slides(db, uid, course, ["qqword"])[0]
    assert (strong.weak, weak.weak, weak.label) == (False, True, "3-4")
    assert all(h.weak for h in search_slides(db, uid, course, ["zzzz"]))  # nothing fits: the closest are shown, all flagged


def test_search_stays_in_one_subject_and_one_account(db, subject, monkeypatch):
    _, uid, course = subject
    assert {h.deck for h in search_slides(db, uid, course, ["Kollisionsdomaenen"], k=20)} <= {"kap3", "skript"}  # not "other" (Algebra)
    sub = f"rag-{uuid.uuid4()}"
    signed_in(monkeypatch, sub)
    assert search_slides(db, user_of(db, sub), course, ["Kollisionsdomaenen"]) == []


def test_search_endpoint_gives_slides_and_exam_tasks_separately(db, subject):
    b, _, _ = subject
    r = b.post("/api/search", json={"subject": "netze", "query": "Kollisionsdomaenen"})
    assert r.status_code == 200
    body = r.json()
    assert body["slides"][0]["label"] == "3-2" and body["slides"][0]["deck"] == "kap3" and body["slides"][0]["weak"] is False
    assert [e["title"] for e in body["exams"]] == ["Klausur 2024"] and body["exams"][0]["subtask_key"]
    assert b.post("/api/search", json={"subject": "Nope", "query": "x"}).json() == {"slides": [], "exams": []}


def test_search_endpoint_needs_sign_in():
    from fastapi.testclient import TestClient

    from main import app

    assert TestClient(app).post("/api/search", json={"subject": "x", "query": "y"}).status_code == 401


def test_lookup_returns_one_link_per_label(db, subject):
    b, _, _ = subject
    links = b.post("/api/materials/lookup", json={"subject": "Netze", "text": "Kollisionsdomaenen Bereich Hubs"}).json()
    assert [(x["title"], x["page"]) for x in links][:1] == [("kap3", 3)] and len({(x["document_id"], x["page"]) for x in links}) == len(links)


def test_idle_worker_backfills_decks_without_page_structure(db, subject):
    _, uid, course = subject
    doc = db.scalar(select(Document).where(Document.user_id == uid, Document.filename == "kap3.pdf"))
    db.execute(delete(DeckPage).where(DeckPage.document_id == doc.id))
    doc.outline = doc.outline_source = None
    db.commit()
    assert all(h.deck != "kap3" for h in search_slides(db, uid, course, ["Kollisionsdomaenen"]))  # unread Deck: nothing to rank yet
    while backfill_decks(db):
        pass
    assert labels(db, uid, course, "Kollisionsdomaenen")[0] == ("3-2", "Kollisionsdomaenen")
    assert backfill_decks(db) == 0


def test_hints_complete_from_titles_only_and_suggest_a_correction(db, subject):
    b = subject[0]

    def hint(text):
        return b.get("/api/search/hints", params={"subject": "Netze", "text": text}).json()

    assert hint("kolli")["completions"] == ["Kollisionsdomaenen"]
    assert "qqword" not in hint("qq")["completions"] and hint("qq")["completions"] == []  # body-only words are not offered
    assert hint("Kollisionsdomaenen ")["completions"] == []  # nothing is being typed
    assert hint("Kollisionsdomaenne ")["suggestion"] == {"word": "Kollisionsdomaenne", "to": "Kollisionsdomaenen"}
    assert hint("wie Kollisionsdomaenen ")["suggestion"] is None  # correct word
    assert hint("Kollisionsdomaene ")["suggestion"] is None  # an ending of the term is still the term
    assert hint("xylophon ")["suggestion"] is None  # unknown word, nothing near
    assert hint("hamm")["completions"] == []  # script text is not a title
    assert b.get("/api/search/hints", params={"subject": "Nope", "text": "kol"}).json() == {"completions": [], "suggestion": None}
    assert b.get("/api/search/hints", params={"subject": "Algebra", "text": "kolli"}).json()["completions"] == [
        "Kollisionsdomaenen"
    ]  # its own Subject's deck


def _vocab(*titles):
    from app.rag.hints import Vocab, _spellings

    v = Vocab()
    for title in titles:
        pairs = list(_spellings(title))
        v.update({t for t, _ in pairs})
        for t, w in pairs:
            v.spelling.setdefault(t, Counter())[w] += 1
    return v


def test_hints_handle_umlauts_and_return_the_slide_spelling():
    from app.rag.hints import hints

    v = _vocab("Größe", "Größe der Kollisionsdomäne", "groesse", "IPv6 und TCP-Handshake")
    assert hints(v, "gr")["completions"] == ["Größe"] and hints(v, "grö")["completions"] == ["Größe"]
    assert hints(v, "Kollisionsdomänn ")["suggestion"] == {"word": "Kollisionsdomänn", "to": "Kollisionsdomäne"}
    assert hints(v, "Größee ")["suggestion"] is None  # an ending of the word is still the word
    assert hints(v, "ipv")["completions"] == ["IPv6"] and hints(v, "tcp-hand")["completions"] == ["TCP-Handshake"]
    assert hints(v, "TCP-Handshke ")["suggestion"] == {"word": "TCP-Handshke", "to": "TCP-Handshake"}
    assert hints(v, "Gro\u0308")["completions"] == ["Größe"]  # decomposed ö, as PDFs and pasted text have it
    assert hints(v, "Count-to-")["completions"] == []  # a dangling hyphen is not a word being completed


def test_hint_spelling_tie_goes_to_the_first_seen():
    from app.rag.hints import hints

    assert hints(_vocab("tcp", "TCP"), "tc")["completions"] == ["tcp"]
    v = _vocab("TCP", "tcp")
    assert v.written("tcp") == "TCP" and hints(v, "tc")["completions"] == ["TCP"]
    assert _vocab("TCP", "tcp", "tcp").written("tcp") == "tcp"  # a higher count still wins
