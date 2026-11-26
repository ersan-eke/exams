import uuid

import pytest
from fastapi.testclient import TestClient

from app.core import config, crypto
from app.core.storage import exam_dir
from app.slack import crops
from main import app

PNG = b"\x89PNG\r\n\x1a\nfake"
tc = TestClient(app)


@pytest.fixture
def crop():
    exam = uuid.uuid4()
    path = exam_dir(exam) / "blank/crops/a.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(PNG)
    return exam, path


def token_from(url: str) -> str:
    return url.rsplit("/", 1)[1]


def test_round_trip(crop):
    _, path = crop
    assert crops.crop_file(token_from(crops.crop_url("https://h", path))) == path


def test_url_is_https_base_plus_token_and_short(crop):
    url = crops.crop_url("https://h", crop[1])
    assert url.startswith("https://h/api/slack/crops/")
    assert len(url) < 3000


def test_bad_tokens_return_none(crop, monkeypatch):
    exam, path = crop
    good = token_from(crops.crop_url("https://h", path))
    bad = ["", "x", good[:-1] + ("A" if good[-1] != "A" else "B")]
    bad += [crypto.encrypt(p) for p in (f"{exam}/blank/../x.png", f"{exam}/other/a.png", "not-a-uuid/blank/a.png")]
    for t in bad:
        assert crops.crop_file(t) is None
    monkeypatch.setattr(crops, "TTL", -1)
    assert crops.crop_file(good) is None


def test_missing_file_returns_none(crop):
    exam, _ = crop
    assert crops.crop_file(crypto.encrypt(f"{exam}/blank/nope.png")) is None


def test_route_serves_png_and_404s_everything_else(crop):
    r = tc.get(f"/api/slack/crops/{token_from(crops.crop_url('https://h', crop[1]))}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert r.content == PNG
    assert tc.get("/api/slack/crops/garbage").status_code == 404


def test_route_404_when_slack_disabled(crop, monkeypatch):
    url = crops.crop_url("https://h", crop[1])
    monkeypatch.setattr(config, "SLACK_ENABLED", False)
    assert tc.get(f"/api/slack/crops/{token_from(url)}").status_code == 404
