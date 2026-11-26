import asyncio
import base64
import functools
import types as pytypes

import anthropic
import httpx
import openai
import pytest
from google.genai import errors as gerrors
from google.genai import types as gtypes

from app.grading.grader import ADAPTERS, Final, GradingError, Thinking
from app.grading.models import GradeIn, LlmOut, llm_schema
from app.grading.prompt import CacheBreak, Image, Text
from app.grading.providers import anthropic as a_mod
from app.grading.providers import google as g_mod
from app.grading.providers import openrouter as o_mod

PNG = b"\x89PNG\r\n\x1a\nxx"
ITEMS = [Text("Q"), Image(PNG), CacheBreak(), Text("A")]
KEY = "sk-secret-key"


def req(provider, model=None):
    return GradeIn(provider=provider, model=model, points=4, question={"text": "Q"}, answer={"text": "A"})


def aio(f):
    @functools.wraps(f)
    def run(*a, **kw):
        return asyncio.run(f(*a, **kw))

    return run


async def collect(agen):
    return [e async for e in agen]


def ns(**kw):
    return pytypes.SimpleNamespace(**kw)


class Client(pytypes.SimpleNamespace):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


def http_err(cls, status):
    r = httpx.Response(status, request=httpx.Request("POST", "http://x"))
    return cls("boom", response=r, body=None)


def test_registered():
    assert {"anthropic", "google", "openrouter"} <= set(ADAPTERS)


# ---- Anthropic ----


class FakeStream:
    def __init__(self, kw, events, msg, err=None):
        self.kw, self.events, self.msg, self.err, self.exited = kw, events, msg, err, False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        self.exited = True

    async def __aiter__(self):
        for e in self.events:
            yield e
        if self.err:
            raise self.err

    async def get_final_message(self):
        return self.msg


def delta(kind, **kw):
    return ns(type="content_block_delta", delta=ns(type=kind, **kw))


def msg(text='{"x":1}', stop="end_turn", model="claude-sonnet-5-5"):
    return ns(content=[ns(type="thinking", thinking="t"), ns(type="text", text=text)], stop_reason=stop, model=model)


@pytest.fixture
def anth(monkeypatch):
    box = ns(stream=None, kw=None, init=None)

    def install(events=(), message=None, err=None):
        def client(**init):
            box.init = init

            def stream(**kw):
                box.stream = FakeStream(kw, events, message or msg(), err)
                box.kw = kw
                return box.stream

            return Client(beta=ns(messages=ns(stream=stream)))

        monkeypatch.setattr(a_mod, "AsyncAnthropic", client)
        return box

    return install


@aio
async def test_anthropic_request(anth):
    box = anth([delta("thinking_delta", thinking="hm"), delta("text_delta", text="{")])
    out = await collect(a_mod.stream(req("anthropic"), KEY, "SYS", ITEMS))
    assert out == [Thinking("hm"), Final('{"x":1}', "claude-sonnet-5-5")]
    kw = box.kw
    assert box.init == {"api_key": KEY}
    assert kw["system"] == [{"type": "text", "text": "SYS"}]
    assert kw["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": llm_schema()}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    blocks = kw["messages"][0]["content"]
    assert blocks[1]["source"] == {"type": "base64", "media_type": "image/png", "data": base64.b64encode(PNG).decode()}
    assert blocks[1]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in blocks[0]
    assert len(blocks) == 3


@aio
async def test_anthropic_haiku_has_no_fallback(anth):
    box = anth()
    await collect(a_mod.stream(req("anthropic", "claude-haiku-5-5"), KEY, "S", ITEMS))
    assert "fallbacks" not in box.kw and "betas" not in box.kw


@pytest.mark.parametrize(
    "exc,code",
    [
        (http_err(anthropic.AuthenticationError, 401), "bad_key"),
        (http_err(anthropic.PermissionDeniedError, 403), "bad_key"),
        (http_err(anthropic.RateLimitError, 429), "rate_limited"),
        (http_err(anthropic.APIStatusError, 402), "no_credits"),
        (http_err(anthropic.APIStatusError, 500), "llm_failed"),
        (http_err(anthropic.APIStatusError, 529), "overloaded"),
        (http_err(anthropic.APIStatusError, 503), "overloaded"),
        (anthropic.APIConnectionError(request=httpx.Request("POST", "http://x")), "llm_failed"),
    ],
)
@aio
async def test_anthropic_errors(anth, exc, code):
    anth(err=exc)
    with pytest.raises(GradingError) as e:
        await collect(a_mod.stream(req("anthropic"), KEY, "S", ITEMS))
    assert e.value.code == code


@aio
async def test_anthropic_refusal(anth):
    anth(message=msg(stop="refusal"))
    with pytest.raises(GradingError) as e:
        await collect(a_mod.stream(req("anthropic"), KEY, "S", ITEMS))
    assert e.value.code == "refused"


@aio
async def test_anthropic_close_midstream(anth):
    box = anth([delta("thinking_delta", thinking="a"), delta("thinking_delta", thinking="b")])
    g = a_mod.stream(req("anthropic"), KEY, "S", ITEMS)
    assert await g.__anext__() == Thinking("a")
    await g.aclose()
    assert box.stream.exited


# ---- Google ----


class FakeGStream:
    def __init__(self, chunks, err=None):
        self.chunks, self.err, self.closed = chunks, err, False

    def __aiter__(self):
        return self._it()

    async def _it(self):
        for c in self.chunks:
            yield c
        if self.err:
            raise self.err

    async def aclose(self):
        self.closed = True


def chunk(*parts, finish=None, block=None):
    cands = [ns(content=ns(parts=list(parts)), finish_reason=finish)] if parts or finish else []
    return ns(candidates=cands, prompt_feedback=ns(block_reason=block) if block else None)


def part(text, thought=False):
    return ns(text=text, thought=thought)


@pytest.fixture
def gem(monkeypatch):
    box = ns(args=None, init=None, stream=None, closed=False)

    def install(chunks=(), err=None, call_err=None):
        async def gen(**kw):
            box.args = kw
            if call_err:
                raise call_err
            box.stream = FakeGStream(list(chunks), err)
            return box.stream

        def client(**init):
            box.init = init

            async def aclose():
                box.closed = True

            return ns(aio=ns(models=ns(generate_content_stream=gen), aclose=aclose))

        monkeypatch.setattr(g_mod.genai, "Client", client)
        return box

    return install


@aio
async def test_google_request(gem):
    box = gem([chunk(part("th", True)), chunk(part('{"a":'), part("1}"))])
    out = await collect(g_mod.stream(req("google"), KEY, "SYS", ITEMS))
    assert out == [Thinking("th"), Final('{"a":1}', "gemini-flash-latest")]
    assert box.init == {"api_key": KEY} and box.args["model"] == "gemini-flash-latest"
    parts = box.args["contents"][0].parts
    assert [p.text for p in parts] == ["Q", None, "A"]
    assert parts[1].inline_data.data == PNG and parts[1].inline_data.mime_type == "image/png"
    cfg = box.args["config"]
    assert cfg.system_instruction == "SYS" and cfg.response_mime_type == "application/json"
    assert cfg.response_schema is LlmOut and cfg.thinking_config.include_thoughts is True
    assert box.closed


@pytest.mark.parametrize(
    "exc,code",
    [
        (
            gerrors.ClientError(
                400, {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}
            ),
            "bad_key",
        ),
        (gerrors.ClientError(400, {"error": {"code": 400, "message": "other", "status": "INVALID_ARGUMENT"}}), "llm_failed"),
        (gerrors.ClientError(401, {"error": {"code": 401, "message": "x", "status": "UNAUTHENTICATED"}}), "bad_key"),
        (gerrors.ClientError(403, {"error": {"code": 403, "message": "x", "status": "PERMISSION_DENIED"}}), "bad_key"),
        (gerrors.ClientError(429, {"error": {"code": 429, "message": "x", "status": "RESOURCE_EXHAUSTED"}}), "rate_limited"),
        (gerrors.ServerError(500, {"error": {"code": 500, "message": "x", "status": "INTERNAL"}}), "llm_failed"),
        (gerrors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}), "overloaded"),
        (gerrors.ServerError(504, {"error": {"code": 504, "message": "x", "status": "DEADLINE_EXCEEDED"}}), "overloaded"),
        (httpx.ConnectError("x"), "llm_failed"),
    ],
)
@pytest.mark.parametrize("where", ["call", "stream"])
@aio
async def test_google_errors(gem, exc, code, where):
    gem(**{"call_err" if where == "call" else "err": exc})
    with pytest.raises(GradingError) as e:
        await collect(g_mod.stream(req("google"), KEY, "S", ITEMS))
    assert e.value.code == code


@pytest.mark.parametrize("c", [chunk(block="SAFETY"), chunk(part("x"), finish=gtypes.FinishReason.SAFETY)])
@aio
async def test_google_refused(gem, c):
    gem([c])
    with pytest.raises(GradingError) as e:
        await collect(g_mod.stream(req("google"), KEY, "S", ITEMS))
    assert e.value.code == "refused"


@aio
async def test_google_close_midstream(gem):
    box = gem([chunk(part("a", True)), chunk(part("b", True))])
    g = g_mod.stream(req("google"), KEY, "S", ITEMS)
    assert await g.__anext__() == Thinking("a")
    await g.aclose()
    assert box.stream.closed


# ---- OpenRouter ----


class FakeOStream:
    def __init__(self, chunks, err=None):
        self.chunks, self.err, self.closed = chunks, err, False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        self.closed = True

    async def __aiter__(self):
        for c in self.chunks:
            yield c
        if self.err:
            raise self.err


def ochunk(content=None, finish=None, model="google/gemini-2.5-flash"):
    return ns(model=model, choices=[ns(delta=ns(content=content), finish_reason=finish)])


@pytest.fixture
def orr(monkeypatch):
    box = ns(init=None, kw=None, stream=None)

    def install(chunks=(), err=None, call_err=None):
        async def create(**kw):
            box.kw = kw
            if call_err:
                raise call_err
            box.stream = FakeOStream(list(chunks), err)
            return box.stream

        def client(**init):
            box.init = init
            return Client(chat=ns(completions=ns(create=create)))

        monkeypatch.setattr(o_mod, "AsyncOpenAI", client)
        return box

    return install


@aio
async def test_openrouter_request(orr):
    box = orr([ns(model="m", choices=[]), ochunk('{"a":'), ochunk("1}", "stop", "served/model")])
    out = await collect(o_mod.stream(req("openrouter"), KEY, "SYS", ITEMS))
    assert out == [Final('{"a":1}', "served/model")]
    assert box.init == {"api_key": KEY, "base_url": "https://openrouter.ai/api/v1"}
    kw = box.kw
    assert kw["stream"] is True and kw["model"] == "google/gemini-2.5-flash"
    assert kw["messages"][0] == {"role": "system", "content": "SYS"}
    assert kw["messages"][1]["content"] == [
        {"type": "text", "text": "Q"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG).decode()}},
        {"type": "text", "text": "A"},
    ]
    assert kw["response_format"] == {"type": "json_schema", "json_schema": {"name": "grade", "strict": True, "schema": llm_schema()}}
    assert kw["extra_body"] == {"provider": {"require_parameters": True}}


@pytest.mark.parametrize(
    "exc,code",
    [
        (http_err(openai.AuthenticationError, 401), "bad_key"),
        (http_err(openai.APIStatusError, 402), "no_credits"),
        (http_err(openai.RateLimitError, 429), "rate_limited"),
        (http_err(openai.APIStatusError, 500), "llm_failed"),
        (http_err(openai.APIStatusError, 502), "overloaded"),
        (http_err(openai.APIStatusError, 503), "overloaded"),
        (openai.APIConnectionError(request=httpx.Request("POST", "http://x")), "llm_failed"),
    ],
)
@pytest.mark.parametrize("where", ["call", "stream"])
@aio
async def test_openrouter_errors(orr, exc, code, where):
    orr(**{"call_err" if where == "call" else "err": exc})
    with pytest.raises(GradingError) as e:
        await collect(o_mod.stream(req("openrouter"), KEY, "S", ITEMS))
    assert e.value.code == code


@aio
async def test_openrouter_content_filter(orr):
    orr([ochunk("x", "content_filter")])
    with pytest.raises(GradingError) as e:
        await collect(o_mod.stream(req("openrouter"), KEY, "S", ITEMS))
    assert e.value.code == "refused"
