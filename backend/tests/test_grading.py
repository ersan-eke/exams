import asyncio
import base64
import json
import logging

import pytest
from pydantic import ValidationError

from app.grading.grader import ADAPTERS, Final, GradingError, Thinking, finalize, grade_stream
from app.grading.models import GradeIn, LlmOut, llm_schema
from app.grading.prompt import SYSTEM_OWN, SYSTEM_SOLUTION, CacheBreak, Image, Text, build_content

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nxx").decode()
OUT = {
    "points": 3,
    "points_min": 2,
    "points_max": 3,
    "feedback": "ok",
    "rubric": [{"item": "a", "max": 4, "hit": 3, "note": "n", "source": "solution"}],
}


def req(**kw):
    base = {"points": 4, "question": {"text": "Q", "images": [PNG]}, "answer": {"text": "A", "images": [PNG]}}
    return GradeIn(**{**base, **kw})


@pytest.fixture
def fake():
    saved = dict(ADAPTERS)
    calls = []

    def install(*events):
        async def adapter(r, key, system, items):
            calls.append((r, key, system, items))
            for e in events:
                if isinstance(e, Exception):
                    raise e
                yield e

        ADAPTERS["anthropic"] = adapter
        return calls

    yield install
    ADAPTERS.clear()
    ADAPTERS.update(saved)


def run(r, key="k"):
    async def go():
        return [e async for e in grade_stream(r, key)]

    return asyncio.run(go())


def test_finalize_clamps_and_orders():
    g = finalize(LlmOut(points=5, points_min=-1, points_max=9, rubric=[], feedback=""), 4, "solution", "anthropic", "m")
    assert (g.points, g.points_min, g.points_max, g.certain) == (4, 0, 4, False)
    g = finalize(LlmOut(points=3, points_min=3.5, points_max=2, rubric=[], feedback=""), 4, "solution", "anthropic", "m")
    assert (g.points_min, g.points_max, g.certain) == (3, 3, True)


def test_basis_follows_solution(fake):
    calls = fake(Final(json.dumps(OUT)))
    ev = run(req(solution={"text": "S"}, model="claude-haiku-5-5"))
    assert calls[0][2] == SYSTEM_SOLUTION and calls[0][1] == "k"
    g = ev[-1]["grade"]
    assert ev[-1]["type"] == "done" and g["basis"] == "solution"
    assert (g["provider"], g["model"]) == ("anthropic", "claude-haiku-5-5")
    calls = fake(Final(json.dumps(OUT)))
    ev = run(req())
    assert calls[-1][2] == SYSTEM_OWN and ev[-1]["grade"]["basis"] == "own_solution"


def test_items_order():
    r = req(solution={"text": "S", "images": [PNG], "rubric": [{"item": "x", "max": 2, "source": "solution"}]})
    items = build_content(r)
    kinds = [type(i) for i in items]
    assert kinds == [Text, Image, Text, Text, Image, CacheBreak, Text, Text, Image]
    assert items[-3].text == "Max points: 4" and "x" in items[3].text
    refs = [{"question": {"text": "RQ"}, "solution": {"text": "RS"}, "points": 2}] * 2
    items = build_content(req(references=refs))
    assert sum(isinstance(i, CacheBreak) for i in items) == 1
    assert [i.text for i in items if isinstance(i, Text)].count("Max points: 4") == 1
    assert sum("RQ" in i.text for i in items if isinstance(i, Text)) == 2


def test_thinking_then_done(fake):
    fake(Thinking("a"), Thinking("b"), Final(json.dumps(OUT)))
    ev = run(req())
    assert [(e["type"], e.get("text")) for e in ev[:2]] == [("thinking", "a"), ("thinking", "b")]
    assert ev[2]["type"] == "done" and len(ev) == 3


@pytest.mark.parametrize("text", ["Sure! Here is the grade: {}", '{"points": 1}'])
def test_invalid_json_is_llm_failed(fake, text):
    fake(Final(text))
    assert run(req()) == [{"type": "error", "code": "llm_failed"}]


def test_adapter_error_code_passes_through(fake):
    fake(GradingError("no_credits"))
    assert run(req()) == [{"type": "error", "code": "no_credits"}]


def test_unexpected_exception_is_llm_failed_and_key_not_logged(fake, caplog):
    key = "sk-secret-123"
    fake(RuntimeError(key))
    with caplog.at_level(logging.DEBUG):
        ev = run(req(), key)
    assert ev == [{"type": "error", "code": "llm_failed"}]
    assert key not in caplog.text and key not in json.dumps(ev)


def test_rejects_bad_input():
    bad = [
        {"answer": {"images": [base64.b64encode(b"nope").decode()]}},
        {"answer": {"images": [PNG] * 21}},
        {"references": [{"question": {}, "solution": {}, "points": 1}] * 4},
        {"points": 0},
        {"provider": "anthropic", "model": "gpt-4o"},
        {"provider": "openrouter", "model": "bad id"},
        {"provider": "openrouter", "model": "a/b\n"},
        {"provider": "openrouter", "model": "gö/b"},
        {"answer": {"text": "x" * 20001}},
    ]
    for kw in bad:
        with pytest.raises(ValidationError):
            req(**kw)
    assert req(provider="google").model == "gemini-flash-latest"
    assert req(provider="openrouter", model="google/gemini-2.5-flash").model == "google/gemini-2.5-flash"


def test_llm_schema_is_strict():
    s = llm_schema()
    assert "$defs" not in json.dumps(s) and "$ref" not in json.dumps(s)
    assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
    item = s["properties"]["rubric"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == set(item["properties"])


def test_finalize_sanitizes_rubric_lines():
    line = lambda mx, hit: {"item": "a", "max": mx, "hit": hit, "note": "", "source": "inferred"}
    out = LlmOut(points=2, points_min=2, points_max=2, feedback="", rubric=[line(3, 5), line(2, -1), line(-1, 1)])
    g = finalize(out, 4, "solution", "anthropic", "m")
    assert [(r.max, r.hit) for r in g.rubric] == [(3, 3), (2, 0), (0, 0)]


@pytest.mark.parametrize("field", ["points", "points_min", "points_max"])
def test_non_finite_is_llm_failed(fake, field):
    fake(Final(json.dumps({**OUT, field: float("nan")})))
    assert run(req()) == [{"type": "error", "code": "llm_failed"}]
    out = {**OUT, "rubric": [{**OUT["rubric"][0], "hit": float("inf")}]}
    fake(Final(json.dumps(out)))
    assert run(req()) == [{"type": "error", "code": "llm_failed"}]


def test_finalize_rejects_non_finite_directly():
    with pytest.raises(ValueError):
        finalize(LlmOut(points=float("nan"), points_min=0, points_max=1, rubric=[], feedback=""), 4, "solution", "anthropic", "m")


def test_stalled_model_times_out(fake, monkeypatch):
    from app.grading import grader

    monkeypatch.setattr(grader, "IDLE_TIMEOUT", 0.05)
    closed = []

    async def stalls(r, key, system, items):
        try:
            yield Thinking("a")
            await asyncio.sleep(10)
        finally:
            closed.append(True)

    ADAPTERS["anthropic"] = stalls
    assert run(req())[-1] == {"type": "error", "code": "timeout"}
    assert closed == [True]


def test_one_log_line_per_request_without_key(fake, caplog, monkeypatch):
    # alembic's fileConfig (run by the db fixture) disables existing loggers; the server never runs it
    monkeypatch.setattr(logging.getLogger("app.grading.grader"), "disabled", False)
    fake(Final(json.dumps(OUT)))
    with caplog.at_level(logging.INFO, logger="app.grading"):
        run(req(), key="sk-secret-123")
    lines = [r.getMessage() for r in caplog.records if r.name == "app.grading.grader"]
    assert len(lines) == 1
    assert "anthropic" in lines[0] and "images=2" in lines[0] and "outcome=done" in lines[0]
    assert "sk-secret-123" not in caplog.text
