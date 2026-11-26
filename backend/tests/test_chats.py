import json
import logging
import threading
import time
import uuid

import anyio
import pytest
from sqlalchemy import select, text
from test_auth import signed_in
from test_rag_ask import add_doc
from test_rag_slides import DECK

from app.core import config
from app.db.models import Chat
from app.db.session import engine
from app.grading.grader import ADAPTERS, Final
from app.grading.limits import ask_limiter
from app.rag.index import index_pending


@pytest.fixture
def chatter(db, monkeypatch):
    b = signed_in(monkeypatch, f"chat-{uuid.uuid4()}")
    add_doc(b, db, DECK, "kap3.pdf", "Netze")
    while index_pending(db):
        pass
    return b


def test_chats_are_created_listed_per_subject_renamed_and_deleted(chatter):
    a = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    other = chatter.post("/api/chats", json={"subject": "Algebra"}).json()
    assert a["title"] == "New chat" and a["messages"] == [] and a["pinned"] == []
    assert [c["id"] for c in chatter.get("/api/chats", params={"subject": "netze"}).json()] == [a["id"]]
    assert chatter.patch(f"/api/chats/{a['id']}", json={"title": " Mein Chat "}).json()["title"] == "Mein Chat"
    assert chatter.patch(f"/api/chats/{a['id']}", json={"title": " "}).status_code == 422
    assert chatter.delete(f"/api/chats/{a['id']}").status_code == 204
    assert chatter.get(f"/api/chats/{a['id']}").status_code == 404
    assert chatter.get(f"/api/chats/{other['id']}").status_code == 200


def test_a_message_is_stored_with_a_search_turn_and_titles_the_chat(chatter):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    r = chatter.post(f"/api/chats/{c['id']}/messages", json={"text": "Kollisionsdomaenen"}).json()
    user, turn = r["messages"]
    assert user == {"role": "user", "text": "Kollisionsdomaenen"} and r["title"] == "Kollisionsdomaenen"
    top = turn["slides"][0]
    assert turn["role"] == "search" and top["label"] == "3-2" and top["terms"] == ["Kollisionsdomaenen".lower()]
    assert {"document_id", "deck", "page", "title", "weak"} <= top.keys()
    again = chatter.post(f"/api/chats/{c['id']}/messages", json={"text": "Hubs"}).json()
    assert len(again["messages"]) == 4 and again["title"] == "Kollisionsdomaenen"  # only the first message titles
    assert chatter.get(f"/api/chats/{c['id']}").json()["messages"] == again["messages"]  # reopening restores it


def test_long_first_message_is_cut_for_the_title(chatter):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    title = chatter.post(f"/api/chats/{c['id']}/messages", json={"text": "wort " * 40}).json()["title"]
    assert len(title) <= 60 and title.endswith("…")


def test_another_users_chat_is_404(chatter, monkeypatch):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    other = signed_in(monkeypatch, f"chat-{uuid.uuid4()}")
    assert other.get("/api/chats", params={"subject": "Netze"}).json() == []
    for call in (
        other.get(f"/api/chats/{c['id']}"),
        other.patch(f"/api/chats/{c['id']}", json={"title": "x"}),
        other.delete(f"/api/chats/{c['id']}"),
        other.post(f"/api/chats/{c['id']}/messages", json={"text": "x"}),
    ):
        assert call.status_code == 404


def test_a_title_chosen_before_the_first_message_stays(chatter):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    chatter.patch(f"/api/chats/{c['id']}", json={"title": "Mein Chat"})
    assert chatter.post(f"/api/chats/{c['id']}/messages", json={"text": "Hubs"}).json()["title"] == "Mein Chat"


def test_messages_waiting_on_the_chat_lock_block_no_other_request_and_both_land(chatter):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    url = f"/api/chats/{c['id']}/messages"
    # one event loop for every request, as under uvicorn (`with chatter` would also run the lifespan, which MCP allows only once);
    # the probe autocommits: inside a transaction it would keep seeing one pg_stat_activity snapshot
    try:
        with (
            anyio.from_thread.start_blocking_portal() as chatter.portal,
            engine.connect() as lock,
            engine.connect().execution_options(isolation_level="AUTOCOMMIT") as probe,
        ):
            lock.execute(select(Chat).where(Chat.id == uuid.UUID(c["id"])).with_for_update())
            holder = lock.execute(text("SELECT pg_backend_pid()")).scalar()
            send = [threading.Thread(target=chatter.post, args=(url,), kwargs={"json": {"text": t}}, daemon=True) for t in ("Hubs", "Switches")]
            for t in send:
                t.start()
            blocked = text("SELECT count(*) FROM pg_stat_activity WHERE :holder = ANY(pg_blocking_pids(pid))")
            deadline = time.monotonic() + 10
            while probe.execute(blocked, {"holder": holder}).scalar() < 1:  # a message is now waiting on this Chat's row lock
                assert time.monotonic() < deadline, "no message reached the row lock"
                time.sleep(0.05)
            other = threading.Thread(target=chatter.get, args=("/api/chats",), kwargs={"params": {"subject": "Netze"}}, daemon=True)
            other.start()
            other.join(5)
            answered = not other.is_alive()
            lock.rollback()
            for t in [*send, other]:
                t.join(10)
    finally:
        chatter.portal = None
    assert answered, "a request waiting on a row lock blocked the event loop"
    texts = {m["text"] for m in chatter.get(f"/api/chats/{c['id']}").json()["messages"] if m["role"] == "user"}
    assert texts == {"Hubs", "Switches"}


@pytest.fixture
def llm(monkeypatch):
    seen = {}
    orig = ADAPTERS["anthropic"]

    async def fake(req, key, system, items, out=None):
        seen.update(key=key, prompt=items[0].text, checked_out=engine.pool.checkedout())
        yield Final(json.dumps({"answer": "Hubs repeat signals.", "cited": [1, 7]}))  # 7 was never pinned

    ADAPTERS["anthropic"] = fake
    ask_limiter.hits.clear()
    yield seen
    ADAPTERS["anthropic"] = orig


def pin_first_slide(b, chat_id, text="Kollisionsdomaenen"):
    turn = b.post(f"/api/chats/{chat_id}/messages", json={"text": text}).json()["messages"][-1]
    s = turn["slides"][0]
    return s, b.put(f"/api/chats/{chat_id}/pinned", json={"pins": [{"document_id": s["document_id"], "page": s["page"]}]})


def test_pins_are_saved_and_foreign_pages_dropped(chatter, monkeypatch):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    s, r = pin_first_slide(chatter, c["id"])
    assert r.json()["pinned"] == [{"document_id": s["document_id"], "page": s["page"]}]
    assert chatter.get(f"/api/chats/{c['id']}").json()["pinned"] == r.json()["pinned"]
    assert chatter.put(f"/api/chats/{c['id']}/pinned", json={"pins": []}).json()["pinned"] == []
    other = signed_in(monkeypatch, f"chat-{uuid.uuid4()}")
    mine = other.post("/api/chats", json={"subject": "Netze"}).json()
    r = other.put(f"/api/chats/{mine['id']}/pinned", json={"pins": [{"document_id": s["document_id"], "page": s["page"]}]})
    assert r.json()["pinned"] == []  # someone else's Deck cannot be pinned


def test_ai_turn_sends_only_pinned_pages_and_the_last_messages_and_cites_only_pins(chatter, llm, caplog):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    for i in range(7):
        chatter.post(f"/api/chats/{c['id']}/messages", json={"text": f"frage{i} Hubs"})
    s, _ = pin_first_slide(chatter, c["id"])
    with caplog.at_level(logging.DEBUG):
        r = chatter.post(f"/api/chats/{c['id']}/ask", json={}, headers={"X-LLM-Key": "sk-secret-key"})
    assert r.status_code == 200, r.text
    ai = r.json()["messages"][-1]
    assert ai["role"] == "ai" and ai["text"] == "Hubs repeat signals." and [x["page"] for x in ai["cited"]] == [s["page"]]
    assert llm["key"] == "sk-secret-key" and "sk-secret-key" not in caplog.text and "sk-secret-key" not in json.dumps(r.json())
    assert "Student: Kollisionsdomaenen" in llm["prompt"] and "frage1" not in llm["prompt"] and "frage2" in llm["prompt"]  # last 6 only
    assert llm["prompt"].count("[1]") == 1 and "[2]" not in llm["prompt"]  # one pinned page


def test_ai_turn_holds_no_db_connection_while_the_llm_answers(chatter, llm):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    pin_first_slide(chatter, c["id"])
    idle = engine.pool.checkedout()  # the test's own session may hold one
    r = chatter.post(f"/api/chats/{c['id']}/ask", json={}, headers={"X-LLM-Key": "k"})
    assert r.status_code == 200, r.text
    assert llm["checked_out"] == idle


def test_ai_turn_errors(chatter, llm):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    url = f"/api/chats/{c['id']}/ask"
    assert chatter.post(url, json={}).json()["detail"] == {"code": "no_key"}
    assert chatter.post(url, json={}, headers={"X-LLM-Key": "k"}).json()["detail"] == {"code": "no_pins"}
    pin_first_slide(chatter, c["id"])
    ask_limiter.limit, old = 0, ask_limiter.limit
    try:
        assert chatter.post(url, json={}, headers={"X-LLM-Key": "k"}).json()["detail"] == {"code": "rate_limited"}
    finally:
        ask_limiter.limit = old


def test_ask_preview_is_dev_only_and_calls_no_llm(chatter, llm, monkeypatch):
    c = chatter.post("/api/chats", json={"subject": "Netze"}).json()
    pin_first_slide(chatter, c["id"])
    url = f"/api/chats/{c['id']}/ask/preview"
    assert chatter.post(url, json={}).status_code == 404
    monkeypatch.setattr(config, "DEV", True)
    r = chatter.post(url, json={}).json()
    assert "Pinned pages" in r["prompt"] and r["system"] and "prompt" not in llm
