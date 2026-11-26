from app.pipeline.smoke import features, select


def summary(**kw):
    base = dict(
        kind="digital", solution=False, status="ok", mc_rule=None, mc=0, mc_keys=0, answer_boxes=0, multipage=0, duration=None, stated=None, issues=[]
    )
    return base | kw


def test_issue_messages_are_grouped_by_kind():
    a = features("gbs", summary(issues=["A2b: empty region"], status="warn"))
    b = features("gbs", summary(issues=["A3a: empty region"], status="warn"))
    assert a == b
    assert "issue:#empty region" in a


def test_select_covers_every_feature_with_few_pdfs():
    results = {
        "grnvs/a.pdf": summary(mc=3),
        "grnvs/b.pdf": summary(mc=2),  # adds nothing over a.pdf
        "grnvs/c.pdf": summary(mc=1, solution=True, mc_keys=1),
        "gdb/d.pdf": {"crash": "ValueError"},
    }
    chosen = select(results)
    assert chosen == ["gdb/d.pdf", "grnvs/c.pdf"]
