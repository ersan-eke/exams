from app.rag.text import clean, tokens


def test_clean_repairs_extraction_damage():
    assert clean("U¨bersetzen und ¨Ubung") == "Übersetzen und Übung"
    assert clean("a(cid:80)bc") == "abc"


def test_tokens_ignore_case_umlaut_spelling_and_hyphens():
    assert tokens("Kollisionsdomänen") == tokens("kollisionsdomaenen") == ["kollisionsdomaenen"]
    assert tokens("Count-to-Infinity") == ["counttoinfinity", "count", "to", "infinity"]
    assert "counttoinfinity" in tokens("count-to-infinity") and "domaene" in tokens("Kollisions-Domäne")
