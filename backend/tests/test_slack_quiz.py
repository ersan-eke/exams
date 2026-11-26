import json
import uuid
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from slack_util import slack_post
from test_db import SAMPLE

from app.core.storage import exam_dir
from app.db.exams import course_id, to_rows
from app.db.models import Exam, Integration, User
from app.pipeline import models as p
from app.slack import blocks, client, quiz
from main import app

CMD = "/api/webhooks/slack/commands"
ACT = "/api/webhooks/slack/interactions"
FORM = "application/x-www-form-urlencoded"
T = SAMPLE.tasks[0]
MC = T.subtasks[0].model_copy(
    update={
        "text": "Which?",
        "solution_text": "because",
        "mc_key": [1],
        "mc_options": [p.McOption(region=0, bbox=T.subtasks[0].mc_options[0].bbox, text=t) for t in ("x", "y", "z")],
    }
)
TXT = T.subtasks[1].model_copy(update={"text": "Explain", "solution_text": "free solution"})
STRUCT = SAMPLE.model_copy(update={"is_solution": False, "tasks": [T.model_copy(update={"subtasks": [MC, TXT]})]})


def post(path, data: dict, **kw):
    return slack_post(TestClient(app), path, urlencode(data).encode(), content_type=FORM, **kw)


def click(s, value, action="answer", user=None):
    team, user = s["team"], user or s["user"]
    payload = {
        "type": "block_actions",
        "team": {"id": team},
        "user": {"id": user},
        "response_url": "https://hooks.slack.test/r",
        "actions": [{"action_id": action, "value": value}],
    }
    return post(ACT, {"payload": json.dumps(payload)})


@pytest.fixture
def seed(db):
    a, b = uuid.uuid4(), uuid.uuid4()
    db.add_all([User(id=a), User(id=b)])
    db.flush()
    e, other = uuid.uuid4(), uuid.uuid4()
    team, slack_user = uuid.uuid4().hex, uuid.uuid4().hex
    db.add(to_rows(e, STRUCT, title="Endterm", user_id=a, course_id=course_id(db, a, "Algo")))
    db.add(to_rows(other, STRUCT, title="Secret", user_id=b, course_id=course_id(db, b, "Hidden Subject")))
    db.add(Integration(user_id=a, provider="slack", workspace_id=team, workspace_name="t", external_user_id=slack_user, access_token="x", scopes=""))
    db.commit()
    return {"exam": e, "other": other, "team": team, "user": slack_user}


@pytest.fixture
def sent(monkeypatch):
    calls = []

    async def fake(url, message, replace_original=True):
        calls.append((url, message, replace_original))

    monkeypatch.setattr(client, "respond", fake)
    return calls


def values(msg):
    return [b["value"] for blk in msg["blocks"] if blk["type"] == "actions" for b in blk["elements"]]


def alltext(msg):
    return json.dumps(msg)


def test_quiz_lists_buttons(db, seed):
    for _ in range(10):  # random pick: the text subtask shows a reveal button instead
        msg = post(CMD, {"team_id": seed["team"], "user_id": seed["user"], "text": "Algo", "command": "/quiz"}).json()
        assert msg["response_type"] == "ephemeral"
        v = values(msg)
        if len(v) == 3:
            assert v == [f"{seed['exam']}/{MC.id}|{i}" for i in range(3)]
            return
    pytest.fail("never picked the MC subtask")


def test_unlinked_gets_connect_only(db, seed):
    r = post(CMD, {"team_id": seed["team"], "user_id": "U9", "text": "Algo", "command": "/quiz"}).json()
    assert "Connect" in r["text"] and "Which?" not in alltext(r) and "Explain" not in alltext(r)


@pytest.mark.parametrize("text", ["", "Nope", "Hidden Subject"])
def test_unknown_or_empty_subject_lists_own_subjects_only(db, seed, text):
    r = alltext(post(CMD, {"team_id": seed["team"], "user_id": seed["user"], "text": text, "command": "/quiz"}).json())
    assert "Algo" in r and "Secret" not in r and "Which?" not in r
    assert "Hidden Subject" not in r


def test_answers(db, seed, sent):
    ref = f"{seed['exam']}/{MC.id}"
    assert click(seed, f"{ref}|1").status_code == 200
    assert click(seed, f"{ref}|0").status_code == 200
    assert click(seed, f"{seed['exam']}/{TXT.id}", "reveal").status_code == 200
    right, wrong, reveal = (alltext(m) for _, m, _ in sent)
    assert "Correct!" in right and "because" in right and "B. y" in right
    assert "Wrong." in wrong and "because" in wrong
    assert "free solution" in reveal and "Correct" not in reveal and "Wrong" not in reveal
    assert sent[0][0] == "https://hooks.slack.test/r"


def test_multi_answer_click_is_not_wrong():
    def task(key):
        return {"solution": {"mc_key": key, "text": ""}}

    assert blocks.verdict(task([1, 2]), 1) == "Right, but more options are correct."
    assert blocks.verdict(task([1, 2]), 0) == "Wrong."
    assert blocks.verdict(task([1]), 1) == "Correct!"


def test_tampered_ref_is_not_found(db, seed, sent):
    assert click(seed, f"{seed['other']}/{MC.id}|1").status_code == 200
    assert "not found" in alltext(sent[0][1]).lower() and "Secret" not in alltext(sent[0][1])


def test_unlinked_click_gets_connect(db, seed, sent):
    click(seed, f"{seed['exam']}/{MC.id}|1", user="U9")
    assert "Connect" in sent[0][1]["text"] and "because" not in alltext(sent[0][1])


def test_long_text_and_many_options():
    task = {
        "id": "r",
        "exam": "E",
        "task": "1",
        "label": "a)",
        "points": 1.0,
        "text": "x" * 5000,
        "task_context_text": "",
        "mc_options": ["o" * 200] * 7,
    }
    bl = blocks.question_blocks(task, [], "http://x")
    assert all(len(b["text"]["text"]) <= 3000 for b in bl if b["type"] == "section")
    acts = [b for b in bl if b["type"] == "actions"]
    assert [len(a["elements"]) for a in acts] == [5, 2]
    assert all(len(e["text"]["text"]) <= 75 for a in acts for e in a["elements"])


@pytest.mark.parametrize("path", [CMD, ACT])
def test_bad_signature_401(db, path):
    assert post(path, {"team_id": "T1"}, secret="wrong").status_code == 401


@pytest.mark.parametrize(
    "data",
    [{}, {"payload": "{nope"}, {"payload": "[]"}, {"payload": "{}"}, {"payload": json.dumps({"actions": []})}],
)
def test_bad_interaction_is_400(db, data):
    assert post(ACT, data).status_code == 400


def test_non_string_value_is_400(db, seed):
    assert click(seed, 5, "answer").status_code == 400


@pytest.mark.parametrize("value,action", [("noseparator", "answer"), ("ref|x", "answer"), ("|1", "answer"), ("r", "other")])
def test_bad_values_are_400(db, seed, value, action):
    assert click(seed, value, action).status_code == 400


def test_command_missing_fields_is_400(db):
    assert post(CMD, {"text": "x"}).status_code == 400


def _task(**kw):
    return {"id": "r", "exam": "E<1>", "task": "1", "label": "a)", "points": 1.0, "text": "t", "task_context_text": "", "mc_options": [], **kw}


def test_mrkdwn_is_escaped():
    task = _task(text="a < b & c > d <!here>", task_context_text="<https://x|label>")
    out = alltext({"b": blocks.question_blocks(task, [], "http://x")})
    assert (
        "a &lt; b &amp; c &gt; d &lt;!here&gt;" in out and "<!here>" not in out and "<https://x|label" not in out and "E<1>" in out
    )  # header is plain_text, not mrkdwn
    sol = {"text": "<!here>", "mc_key": None}
    assert "<!here>" not in alltext({"b": blocks.answer_blocks(_task(solution=sol), "r", None, [], [], "http://x")})


def test_fallback_text_survives_long_text():
    bl = blocks.question_blocks(_task(text="x" * 5000), [], "http://x")
    assert all(len(b["text"]["text"]) <= 3000 for b in bl if b["type"] == "section")


PNG = b"\x89PNG"


def crops(seed, *names, layer="blank"):
    d = exam_dir(seed["exam"]) / layer / "crops"
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(PNG)


@pytest.fixture
def mc_only(monkeypatch):
    monkeypatch.setattr(quiz.random, "choice", lambda rows: next(r for r in rows if r["id"].endswith(MC.id)))


def ask(seed):
    return post(CMD, {"team_id": seed["team"], "user_id": seed["user"], "text": "Algo", "command": "/quiz"}).json()["blocks"]


def test_question_has_header_divider_images_buttons_link(seed, mc_only):
    crops(seed, "a.png")
    out = ask(seed)
    assert [b["type"] for b in out] == ["header", "divider", "image", "actions", "context"]
    assert out[2]["image_url"].startswith("http://testserver/api/slack/crops/")
    assert "Which?" not in alltext({"b": out})
    assert f"http://testserver/exams/{seed['exam']}/view" in alltext(out[-1])


def test_question_shows_context_crops_first(seed, mc_only):
    crops(seed, "a.png", "ctx.png")
    out = ask(seed)
    assert [b["type"] for b in out] == ["header", "divider", "image", "image", "actions", "context"]
    assert out[2]["image_url"] != out[3]["image_url"]


def test_missing_crop_files_fall_back_to_text(seed, mc_only):
    out = ask(seed)
    assert [b["type"] for b in out] == ["header", "divider", "section", "actions", "context"]
    assert "Which?" in out[2]["text"]["text"]


def test_many_images_stay_under_50_blocks():
    urls = ["http://x/i.png"] * 60
    for opts in (3, 40):
        out = blocks.question_blocks(_task(mc_options=["o"] * opts), urls, "http://x")
        assert len(out) <= 50 and any(b["type"] == "actions" for b in out)


def test_header_cut_to_150():
    assert len(blocks.question_blocks(_task(exam="E" * 300), [], "http://x")[0]["text"]["text"]) <= 150


def test_answer_keeps_question_and_separates_solution(seed, sent):
    crops(seed, "a.png")
    click(seed, f"{seed['exam']}/{MC.id}|0")
    out = sent[-1][1]["blocks"]
    assert [b["type"] for b in out] == ["header", "divider", "image", "divider", "section", "context"]
    assert out[2]["image_url"].startswith("http://testserver/api/slack/crops/")
    assert "Wrong." in alltext(out[4]) and "because" in alltext(out[4])


def test_solution_crops_follow_solution_text(seed, sent, db):
    crops(seed, "a.png")
    crops(seed, "a.png", layer="ink")
    db.get(Exam, seed["exam"]).has_ink = True
    db.commit()
    click(seed, f"{seed['exam']}/{MC.id}|1")
    types = [b["type"] for b in sent[-1][1]["blocks"]]
    assert types == ["header", "divider", "image", "divider", "section", "image", "context"]
    assert "because" not in alltext(sent[-1][1]) and "Correct!" in alltext(sent[-1][1])


def test_text_only_answer_keeps_fallback_text(seed, sent):
    click(seed, f"{seed['exam']}/{MC.id}|1")
    out = sent[-1][1]["blocks"]
    assert [b["type"] for b in out[:4]] == ["header", "divider", "section", "divider"]
    assert "Which?" in out[2]["text"]["text"] and "because" in alltext(sent[-1][1])


def test_answer_blocks_stay_under_50():
    urls = ["http://x/i.png"] * 60
    task = _task(solution={"text": "s", "mc_key": None})
    assert len(blocks.answer_blocks(task, "r", None, urls, urls, "http://x")) <= 50


def test_answer_without_text_or_verdict_skips_empty_section():
    task = _task(solution={"text": "s", "mc_key": None})
    out = blocks.answer_blocks(task, "r", None, [], ["http://x/i.png"], "http://x")
    assert [b["type"] for b in out[-3:]] == ["divider", "image", "context"]


def test_command_acks_and_posts_via_response_url(db, seed, sent):
    r = post(
        CMD, {"team_id": seed["team"], "user_id": seed["user"], "text": "Algo", "command": "/quiz", "response_url": "https://hooks.slack.test/c"}
    )
    assert r.status_code == 200 and r.content == b""
    assert sent[0][0] == "https://hooks.slack.test/c" and sent[0][1]["response_type"] == "ephemeral" and sent[0][2] is False


def test_respond_logs_body_on_error(monkeypatch, caplog):
    import asyncio

    import httpx

    handler = lambda req: httpx.Response(400, text="invalid_blocks")
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    asyncio.run(client.respond("https://hooks.slack.com/x", {"text": "t"}, False))
    assert "invalid_blocks" in caplog.text


def test_respond_refuses_other_hosts(monkeypatch, caplog):
    import asyncio

    import httpx

    called = []
    real = httpx.AsyncClient
    handler = lambda req: called.append(req) or httpx.Response(200)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    asyncio.run(client.respond("http://169.254.169.254/x", {"text": "t"}))
    assert not called and "unexpected response_url" in caplog.text
