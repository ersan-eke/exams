import base64
import json
import logging

import httpx
import pytest

from app.core import config
from app.notion import client

TOKEN = "secret_tok_123"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Fake clock: sleep advances it, so pacing is observable."""
    c = {"now": 1000.0, "sleeps": []}
    monkeypatch.setattr(client.time, "monotonic", lambda: c["now"])

    def sleep(s):
        c["sleeps"].append(s)
        c["now"] += s

    monkeypatch.setattr(client.time, "sleep", sleep)
    monkeypatch.setattr(client, "_last", 0.0)
    return c


def mock(handler):
    reqs = []

    def h(request):
        reqs.append(request)
        return handler(request, len(reqs))

    return httpx.MockTransport(h), reqs


def body(r):
    return json.loads(r.content)


def test_create_database_schema_and_views():
    def handler(r, n):
        if r.url.path == "/v1/databases":
            return httpx.Response(200, json={"id": "db1", "url": "https://notion.so/db1", "data_sources": [{"id": "ds1", "name": "x"}]})
        if r.url.path == "/v1/data_sources/ds1":
            return httpx.Response(
                200, json={"properties": {k: {"id": k[:2].lower(), "type": "select"} for k in ("Status", "Subject", "Exam", "Task")}}
            )
        return httpx.Response(200, json={"id": f"v{n}"})

    t, reqs = mock(handler)
    assert client.create_database(TOKEN, transport=t) == ("db1", "ds1", "https://notion.so/db1")
    assert [(r.method, r.url.path) for r in reqs] == [
        ("POST", "/v1/databases"),
        ("GET", "/v1/data_sources/ds1"),
    ] + [("POST", "/v1/views")] * 5
    assert all(r.headers["Notion-Version"] == "2026-03-11" and r.headers["Authorization"] == f"Bearer {TOKEN}" for r in reqs)
    db = body(reqs[0])
    assert db["parent"] == {"type": "workspace", "workspace": True} and db["is_inline"] is False
    assert db["title"][0]["text"]["content"] == "Flashcards: exam-sim"
    opts = lambda *names: {"select": {"options": [{"name": n} for n in names]}}
    assert db["initial_data_source"]["properties"] == {
        "Question": {"title": {}},
        "Subject": opts(),
        "Exam": opts(),
        "Task": opts(),
        "Type": opts("Multiple choice", "Open"),
        "Score %": {"number": {"format": "percent"}},
        "Status": opts("New", "Learning", "Known"),
    }
    views = [body(r) for r in reqs[2:]]
    assert all((v["database_id"], v["data_source_id"]) == ("db1", "ds1") and v["type"] == v["configuration"]["type"] for v in views)
    g = lambda pid, sort="ascending": {"type": "select", "property_id": pid, "sort": {"type": sort}}
    assert [(v["name"], v["configuration"]) for v in views] == [
        ("Board", {"type": "board", "group_by": g("st", "manual")}),
        ("Gallery", {"type": "gallery", "cover": {"type": "page_content"}, "cover_size": "large", "cover_aspect": "contain"}),
        ("By subject", {"type": "table", "group_by": g("su"), "wrap_cells": False}),
        ("By exam", {"type": "table", "group_by": g("ex"), "wrap_cells": False}),
        ("Exam × Task", {"type": "board", "group_by": g("ex"), "sub_group_by": g("ta"), "card_layout": "compact"}),
    ]


def test_upload_image_two_requests_and_id(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNGdata")

    def handler(r, n):
        return httpx.Response(200, json={"id": "fu1"})

    t, reqs = mock(handler)
    assert client.upload_image(TOKEN, p, transport=t) == "fu1"
    assert [r.url.path for r in reqs] == ["/v1/file_uploads", "/v1/file_uploads/fu1/send"]
    assert body(reqs[0]) == {"mode": "single_part", "filename": "a.png", "content_type": "image/png"}
    assert reqs[1].headers["content-type"].startswith("multipart/form-data")
    assert b'name="file"' in reqs[1].content and b"\x89PNGdata" in reqs[1].content


def test_upload_skips_missing_or_large_file(tmp_path, monkeypatch):
    t, reqs = mock(lambda r, n: httpx.Response(200, json={"id": "x"}))
    assert client.upload_image(TOKEN, tmp_path / "nope.png", transport=t) is None
    big = tmp_path / "big.png"
    big.write_bytes(b"x" * 10)
    monkeypatch.setattr(client, "MAX_FILE", 5)
    assert client.upload_image(TOKEN, big, transport=t) is None
    assert reqs == []


def test_create_page_uses_data_source_parent():
    t, reqs = mock(lambda r, n: httpx.Response(200, json={"id": "pg1"}))
    props, kids = {"Question": {"title": []}}, [{"type": "divider", "divider": {}}]
    assert client.create_page(TOKEN, "ds1", props, kids, transport=t) == "pg1"
    assert reqs[0].url.path == "/v1/pages"
    assert body(reqs[0]) == {"parent": {"type": "data_source_id", "data_source_id": "ds1"}, "properties": props, "children": kids}


def test_requests_are_spaced(clock):
    t, _ = mock(lambda r, n: httpx.Response(200, json={"id": "p"}))
    for _ in range(3):
        client.create_page(TOKEN, "ds", {}, [], transport=t)
    assert len(clock["sleeps"]) == 2 and all(x >= client.MIN_GAP - 1e-9 for x in clock["sleeps"][1:])


def test_429_waits_retry_after_then_succeeds(clock):
    t, reqs = mock(
        lambda r, n: (
            httpx.Response(429, headers={"Retry-After": "7"}, json={"code": "rate_limited"}) if n == 1 else httpx.Response(200, json={"id": "p"})
        )
    )
    assert client.create_page(TOKEN, "ds", {}, [], transport=t) == "p"
    assert len(reqs) == 2 and 7 in clock["sleeps"]


def test_retry_after_is_capped_and_defaults(clock):
    t, _ = mock(
        lambda r, n: (
            httpx.Response(503, headers={"Retry-After": "999"})
            if n == 1
            else httpx.Response(502)
            if n == 2
            else httpx.Response(200, json={"id": "p"})
        )
    )
    client.create_page(TOKEN, "ds", {}, [], transport=t)
    assert 30 in clock["sleeps"] and 1 in clock["sleeps"]


def test_negative_or_nan_retry_after(clock):
    headers = iter(["-5", "nan"])
    t, _ = mock(lambda r, n: httpx.Response(429, headers={"Retry-After": next(headers)}) if n < 3 else httpx.Response(200, json={"id": "p"}))
    client.create_page(TOKEN, "ds", {}, [], transport=t)
    waits = [s for s in clock["sleeps"] if s in (0, 1)]
    assert 0 in waits and 1 in waits and all(s >= 0 for s in clock["sleeps"])


def test_five_failures_raise_notion_error():
    t, reqs = mock(lambda r, n: httpx.Response(500, json={"code": "internal_server_error", "message": "boom"}))
    with pytest.raises(client.NotionError) as e:
        client.create_page(TOKEN, "ds", {}, [], transport=t)
    assert len(reqs) == 5 and (e.value.status, e.value.code) == (500, "internal_server_error")


def test_401_is_notion_auth():
    t, _ = mock(lambda r, n: httpx.Response(401, json={"code": "unauthorized"}))
    with pytest.raises(client.NotionAuth):
        client.create_page(TOKEN, "ds", {}, [], transport=t)


def test_404_is_notion_gone():
    t, _ = mock(lambda r, n: httpx.Response(404, json={"code": "object_not_found"}))
    with pytest.raises(client.NotionGone):
        client.create_page(TOKEN, "ds", {}, [], transport=t)


def test_archived_parent_is_notion_gone():
    t, _ = mock(lambda r, n: httpx.Response(400, json={"code": "validation_error", "message": "Can't edit block that is archived."}))
    with pytest.raises(client.NotionGone):
        client.create_page(TOKEN, "ds", {}, [], transport=t)
    t, _ = mock(lambda r, n: httpx.Response(400, json={"code": "validation_error", "message": "bad property"}))
    with pytest.raises(client.NotionError):
        client.create_page(TOKEN, "ds", {}, [], transport=t)


def test_refresh_sends_basic_auth_json(monkeypatch):
    monkeypatch.setattr(config, "NOTION", ("cid", "csec"))
    resp = {
        "access_token": "a2",
        "refresh_token": "r2",
        "expires_in": 3600,
        "workspace_id": "w",
        "workspace_name": "W",
        "owner": {"user": {"id": "u"}},
    }
    t, reqs = mock(lambda r, n: httpx.Response(200, json=resp))
    out = client.refresh("r1", transport=t)
    assert out == {
        "access_token": "a2",
        "refresh_token": "r2",
        "expires_in": 3600,
        "workspace_id": "w",
        "workspace_name": "W",
        "external_user_id": "u",
    }
    r = reqs[0]
    assert r.url.path == "/v1/oauth/token" and r.headers["Notion-Version"] == "2026-03-11"
    assert r.headers["Authorization"] == "Basic " + base64.b64encode(b"cid:csec").decode()
    assert body(r) == {"grant_type": "refresh_token", "refresh_token": "r1"}


def test_errors_never_contain_the_token(caplog):
    caplog.set_level(logging.DEBUG)
    for status in (401, 404, 400, 500):
        t, _ = mock(lambda r, n, status=status: httpx.Response(status, json={"code": "c", "message": f"echo {TOKEN}"}))
        with pytest.raises(client.NotionError) as e:
            client.create_page(TOKEN, "ds", {}, [], transport=t)
        assert TOKEN not in str(e.value) and TOKEN not in repr(e.value)
    assert TOKEN not in caplog.text


def test_refresh_tolerates_missing_fields(monkeypatch):
    monkeypatch.setattr(config, "NOTION", ("cid", "csec"))
    t, _ = mock(lambda r, n: httpx.Response(200, json={"access_token": "a2", "refresh_token": "r2", "expires_in": 3600}))
    assert client.refresh("r1", transport=t) == {
        "access_token": "a2",
        "refresh_token": "r2",
        "expires_in": 3600,
        "workspace_id": None,
        "workspace_name": None,
        "external_user_id": None,
    }


def test_oauth_error_field_becomes_code(monkeypatch):
    monkeypatch.setattr(config, "NOTION", ("cid", "csec"))
    t, _ = mock(lambda r, n: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(client.NotionError) as e:
        client.refresh("r1", transport=t)
    assert (e.value.status, e.value.code) == (400, "invalid_grant")


def test_view_failure_keeps_the_database_ids():
    def handler(r, n):
        if r.url.path == "/v1/databases":
            return httpx.Response(200, json={"id": "db1", "url": "u", "data_sources": [{"id": "ds1"}]})
        if r.url.path == "/v1/data_sources/ds1":
            return httpx.Response(200, json={"properties": {"Status": {"id": "s"}}})
        return httpx.Response(400, json={"code": "validation_error"})

    t, _ = mock(handler)
    assert client.create_database(TOKEN, transport=t) == ("db1", "ds1", "u")
