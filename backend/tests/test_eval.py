from app.grading.models import GradeOut
from evals.grading.run_eval import metrics


def out(points, lo, hi, certain=True):
    return GradeOut(
        points=points, points_min=lo, points_max=hi, rubric=[], feedback="", certain=certain, basis="solution", provider="anthropic", model="m"
    )


def test_metrics():
    m = metrics([(2, out(2, 2, 2)), (1, out(3, 0, 4, certain=False)), (4, out(2, 2, 2))])
    assert m["n"] == 3
    assert abs(m["exact"] - 1 / 3) < 1e-9
    assert abs(m["in_range"] - 2 / 3) < 1e-9
    assert abs(m["mae"] - 4 / 3) < 1e-9
    assert m["calibration"] == 0.5
    assert metrics([(1, out(2, 2, 2, certain=False))])["calibration"] is None


def test_metrics_within():
    m = metrics([(2, out(2, 2, 2)), (1, out(1.5, 1.5, 1.5)), (4, out(2, 2, 2))])
    assert abs(m["within_half"] - 2 / 3) < 1e-9
    assert abs(m["within_one"] - 2 / 3) < 1e-9
    assert metrics([])["within_half"] is None and metrics([])["within_one"] is None


def test_main_runs_both_modes(tmp_path, monkeypatch):
    import json

    from evals.grading import run_eval

    q = {"text": "q"}
    cases = [
        {"id": "a", "expected": 1, "request": {"points": 2, "question": q, "answer": {"text": "x"}, "solution": {"text": "s"}}},
        {"id": "b", "expected": 1, "request": {"points": 2, "question": q, "answer": {"text": "x"}}},
    ]
    f = tmp_path / "cases.jsonl"
    f.write_text("\n".join(json.dumps(c) for c in cases))
    calls = []

    async def fake(req, key):
        calls.append(req.solution is not None)
        return out(1, 1, 1).model_copy(update={"basis": "solution" if req.solution else "own_solution"})

    monkeypatch.setattr(run_eval, "grade", fake)
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path / "res")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    path = run_eval.main([str(f)])
    assert calls == [True, False, False]
    assert path.exists() and "own_solution | 2" in path.read_text()


def test_limit_flag(tmp_path, monkeypatch):
    import json

    from evals.grading import run_eval

    q = {"text": "q"}
    cases = [
        {"id": "a", "expected": 1, "request": {"points": 2, "question": q, "answer": {"text": "x"}, "solution": {"text": "s"}}},
        {"id": "b", "expected": 1, "request": {"points": 2, "question": q, "answer": {"text": "x"}}},
    ]
    f = tmp_path / "cases.jsonl"
    f.write_text("\n".join(json.dumps(c) for c in cases))
    calls = []

    async def fake(req, key):
        calls.append(req.solution is not None)
        return out(1, 1, 1).model_copy(update={"basis": "solution" if req.solution else "own_solution"})

    monkeypatch.setattr(run_eval, "grade", fake)
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path / "res")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    path = run_eval.main([str(f), "--limit", "1"])
    assert calls == [True, False]
    assert "- cases: 1" in path.read_text()
