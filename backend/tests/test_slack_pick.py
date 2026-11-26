import uuid

from app.slack import quiz


def test_unattempted_questions_are_not_always_the_first_ones(monkeypatch):
    rows = [{"id": f"{uuid.uuid4()}/k{i}", "preview": "q", "last_score_share": None} for i in range(50)]
    task = {"id": "x/k0", "exam": "E", "task": "T", "label": "l", "text": "t", "mc_options": [], "task_context_text": ""}
    monkeypatch.setattr(quiz.tools, "find_tasks", lambda *a, **k: rows)
    monkeypatch.setattr(quiz.tools, "get_task", lambda *a: (task, []))
    monkeypatch.setattr(quiz.tools, "context_crops", lambda *a: [])
    seen = []
    monkeypatch.setattr(quiz.random, "choice", lambda r: seen.append({x["id"] for x in r}) or r[0])
    for _ in range(5):
        quiz.question(None, uuid.uuid4(), "s", "http://h")
    assert len(set().union(*seen)) > 10  # random tiebreak: not the same ten every time


def test_question_picks_among_the_weakest_and_links_to_the_subtask(monkeypatch):
    exam = uuid.uuid4()
    shares = [0.9, None, 0.1, 0.5, 0.3]
    rows = [{"id": f"{exam}/k{i}", "preview": "q", "last_score_share": s} for i, s in enumerate(shares)]
    task = {"id": f"{exam}/k2", "exam": "E", "task": "T", "label": "l", "text": "t", "mc_options": [], "task_context_text": ""}
    monkeypatch.setattr(quiz.tools, "find_tasks", lambda *a, **k: rows)
    monkeypatch.setattr(quiz.tools, "get_task", lambda *a: (task, []))
    monkeypatch.setattr(quiz.tools, "context_crops", lambda *a: [])
    monkeypatch.setattr(quiz, "WEAKEST", 2)
    seen = []
    monkeypatch.setattr(quiz.random, "choice", lambda r: seen.append([x["id"].split("/")[1] for x in r]) or r[0])
    out = quiz.question(None, uuid.uuid4(), "s", "http://h")
    assert seen == [["k2", "k4"]]  # 0.1 and 0.3 are the weakest; never attempted counts as 0.5
    assert f"/exams/{exam}/view?subtask=k2" in str(out["blocks"][-1])
