import pytest

from app.core.config import parse_allowed_emails


def test_allowlist_strips_lowercases_and_skips_empty():
    assert parse_allowed_emails(" Me@X.com , ,b@y.com") == {"me@x.com", "b@y.com"}
    assert parse_allowed_emails("") == parse_allowed_emails("  ") == frozenset()


@pytest.mark.parametrize("raw", [",", " , "])
def test_allowlist_that_parses_empty_refuses_to_start(raw):
    with pytest.raises(ValueError, match="ALLOWED_EMAILS"):
        parse_allowed_emails(raw)
