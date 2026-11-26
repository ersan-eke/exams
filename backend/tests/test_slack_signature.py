import pytest

from app.slack.signature import sign, verify

S, T, B = "secret", "1700000000", b"text=hi"
NOW = 1700000000.0


def test_valid_signature_passes():
    assert verify(S, T, sign(S, T, B), B, NOW)


def test_wrong_secret_fails():
    assert not verify("other", T, sign(S, T, B), B, NOW)


def test_body_tampered_fails():
    assert not verify(S, T, sign(S, T, B), B + b"x", NOW)


def test_stale_timestamp_fails():
    assert not verify(S, T, sign(S, T, B), B, NOW + 301)


def test_future_timestamp_fails():
    assert not verify(S, T, sign(S, T, B), B, NOW - 301)


def test_boundary_299s_passes():
    assert verify(S, T, sign(S, T, B), B, NOW + 299)
    assert verify(S, T, sign(S, T, B), B, NOW - 299)


@pytest.mark.parametrize("ts", [None, "", "abc", "1e9", "9" * 400])
@pytest.mark.parametrize("sig", [None, "", "v0=", "v1=abc", "v0=zz", "v0=ü"])
def test_missing_or_garbage_inputs_fail(ts, sig):
    assert verify(S, ts, sig, B, NOW) is False


def test_non_ascii_body():
    b = "text=Algorithmen+für+Ärzte".encode()
    assert verify(S, T, sign(S, T, b), b, NOW)
