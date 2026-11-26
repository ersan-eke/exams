from app.notion.cards import CUT, build_card


def q(**kw):
    return {"exam": "Exam 1", "task": "Task 2", "label": "a)", "task_context_text": "CTX", "text": "What?", "mc_options": [], **kw}


def a(text="", mc_key=None):
    return {"solution": {"text": text, "mc_key": mc_key}}


def texts(blocks):
    return [r["text"]["content"] for b in blocks for r in b[b["type"]].get("rich_text", [])]


def test_properties_match_the_schema():
    props, _ = build_card(q(), a("s"), 0.4, "Math", [], [])
    assert props == {
        "Question": {"title": [{"type": "text", "text": {"content": "Exam 1 · Task 2 a)"}}]},
        "Subject": {"select": {"name": "Math"}},
        "Exam": {"select": {"name": "Exam 1"}},
        "Task": {"select": {"name": "Task 2"}},
        "Type": {"select": {"name": "Open"}},
        "Score %": {"number": 0.4},
        "Status": {"select": {"name": "New"}},
    }
    assert build_card(q(mc_options=["x"]), a(), 0.4, "Math", [], [])[0]["Type"] == {"select": {"name": "Multiple choice"}}
    assert "Task" not in build_card(q(task=""), a(), 0.4, "Math", [], [])[0]  # an empty select name is refused by Notion


def test_select_names_are_capped_at_100():
    props, _ = build_card(q(exam="E" * 150), a(), 0.4, "S," * 80, [], [])
    assert props["Exam"]["select"]["name"] == "E" * 100
    assert props["Subject"]["select"]["name"] == "S " * 50


def test_question_crops_hide_the_text():
    _, kids = build_card(q(mc_options=["x"]), a("s"), 0.4, "M", ["u1"], [])
    assert [k["type"] for k in kids] == ["image", "toggle"]
    assert kids[0]["image"] == {"type": "file_upload", "file_upload": {"id": "u1"}}


def test_text_fallback_without_crops():
    _, kids = build_card(q(mc_options=["x", "y"]), a("s"), 0.4, "M", [], [])
    assert texts(kids[:-1]) == ["CTX", "What?", "A. x", "B. y"]


def test_answer_lives_in_the_toggle():
    _, kids = build_card(q(), a("sol", [0]), 0.4, "M", ["u1"], ["s1"])
    assert [k["type"] for k in kids] == ["image", "toggle"]
    assert kids[1]["toggle"]["children"][0]["type"] == "image"
    _, kids = build_card(q(), a("sol", [0]), 0.4, "M", ["u1"], [])
    assert texts(kids[:-1]) == [] and texts(kids[1]["toggle"]["children"]) == ["sol", "Correct: A"]


def test_mc_key_shows_letters():
    _, kids = build_card(q(mc_options=["x", "y"]), a(mc_key=[1]), 0.4, "M", ["u1"], [])
    assert texts(kids[-1]["toggle"]["children"]) == ["Correct: B"]
    _, kids = build_card(q(mc_options=["x", "y"]), a(mc_key=[1]), 0.4, "M", ["u1"], ["s1"])
    assert texts(kids[-1]["toggle"]["children"]) == []


def test_no_solution_note():
    _, kids = build_card(q(), a(), 0.4, "M", ["u1"], [])
    assert texts(kids[-1]["toggle"]["children"]) == ["No solution stored."]


def test_long_text_split_at_2000():
    _, kids = build_card(q(text="x" * 4500), a(), 0.4, "M", [], [])
    assert [len(t) for t in texts(kids[1:2])] == [2000, 2000, 500]


def test_children_capped_at_100():
    _, kids = build_card(q(), a(), 0.4, "M", [f"u{i}" for i in range(150)], [f"s{i}" for i in range(150)])
    assert len(kids) == 100 and kids[-1]["type"] == "toggle"
    assert texts(kids[-2:-1]) == [CUT]
    inner = kids[-1]["toggle"]["children"]
    assert len(inner) == 100 and texts(inner[-1:]) == [CUT]
