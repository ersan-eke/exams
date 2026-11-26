import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from types import SimpleNamespace

from pydantic import BaseModel

from .models import GradeIn, GradeOut, LlmOut, Provider
from .prompt import Item, build_content, system_for

log = logging.getLogger(__name__)


# the provider is busy rather than broken: 502/503/504, and Anthropic's 529 "overloaded"
OVERLOADED = {502, 503, 504, 529}


class GradingError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Thinking:
    text: str


@dataclass(frozen=True)
class Final:
    text: str
    model: str | None = None  # the model that actually answered, if it differs from the request (fallbacks)


Adapter = Callable[[GradeIn, str, str, list[Item]], AsyncIterator[Thinking | Final]]
ADAPTERS: dict[Provider, Adapter] = {}


def finalize(out: LlmOut, max_points: float, basis, provider, model) -> GradeOut:
    """The model's numbers are never trusted: reject non-finite ones, clamp to 0..max, keep min <= points <= max."""
    nums = [out.points, out.points_min, out.points_max, *(v for r in out.rubric for v in (r.max, r.hit))]
    if not all(math.isfinite(v) for v in nums):
        raise ValueError("non-finite number")
    clamp = lambda v, hi: min(max(v, 0), hi)
    points = clamp(out.points, max_points)
    lo, hi = min(clamp(out.points_min, max_points), points), max(clamp(out.points_max, max_points), points)
    rubric = [r.model_copy(update={"max": clamp(r.max, math.inf), "hit": clamp(r.hit, max(r.max, 0))}) for r in out.rubric]
    return GradeOut(
        **out.model_dump() | {"points": points, "points_min": lo, "points_max": hi, "rubric": rubric},
        certain=lo == hi,
        basis=basis,
        provider=provider,
        model=model,
    )


IDLE_TIMEOUT = 120.0  # seconds without any event from the model before giving up


def _image_count(req: GradeIn) -> int:
    parts = [req.question, req.answer, *([req.solution] if req.solution else [])]
    parts += [p for r in req.references for p in (r.question, r.solution)]
    return sum(len(p.images) for p in parts)


async def grade_stream(req: GradeIn, key: str) -> AsyncIterator[dict]:
    start = time.monotonic()
    outcome = "cancelled"
    try:
        async for ev in _grade_events(req, key):
            outcome = ev["type"] if ev["type"] != "error" else ev["code"]
            yield ev
    finally:
        # one line per request so a slow or failing provider shows up in the server log; never the key
        log.info(
            "grade provider=%s model=%s images=%d seconds=%.1f outcome=%s",
            req.provider,
            req.model,
            _image_count(req),
            time.monotonic() - start,
            outcome,
        )


async def _grade_events(req: GradeIn, key: str) -> AsyncIterator[dict]:
    try:
        final = None
        events = ADAPTERS[req.provider](req, key, system_for(req), build_content(req))
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(anext(events), IDLE_TIMEOUT)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    raise GradingError("timeout") from None
                if isinstance(ev, Thinking):
                    yield {"type": "thinking", "text": ev.text}
                else:
                    final = ev
        finally:
            await events.aclose()
        if final is None:
            raise GradingError("llm_failed")
        out = LlmOut.model_validate_json(final.text)
        basis = "solution" if req.solution else "own_solution"
        grade = finalize(out, req.points, basis, req.provider, final.model or req.model)
    except GradingError as e:
        yield {"type": "error", "code": e.code}
        return
    except Exception as e:  # only the type is logged: messages can echo the key
        log.warning("grading failed: %s", type(e).__name__)
        yield {"type": "error", "code": "llm_failed"}
        return
    yield {"type": "done", "grade": grade.model_dump()}


async def complete[T: BaseModel](provider: Provider, model: str, key: str, system: str, items: list[Item], out: type[T]) -> T:
    """One structured answer (no thinking events) from any provider, for callers other than grading. Raises GradingError."""
    events = ADAPTERS[provider](SimpleNamespace(model=model), key, system, items, out)
    final = None
    try:
        while True:
            try:
                ev = await asyncio.wait_for(anext(events), IDLE_TIMEOUT)
            except StopAsyncIteration:
                break
            except TimeoutError:
                raise GradingError("timeout") from None
            if isinstance(ev, Final):
                final = ev
    except GradingError:
        raise
    except Exception as e:  # only the type is logged: messages can echo the key
        log.warning("completion failed: %s", type(e).__name__)
        raise GradingError("llm_failed") from None
    finally:
        await events.aclose()
    if final is None:
        raise GradingError("llm_failed")
    try:
        return out.model_validate_json(final.text)
    except ValueError:
        raise GradingError("llm_failed") from None


async def grade(req: GradeIn, key: str) -> GradeOut:
    async for ev in grade_stream(req, key):
        if ev["type"] == "error":
            raise GradingError(ev["code"])
        if ev["type"] == "done":
            return GradeOut(**ev["grade"])
    raise GradingError("llm_failed")


from . import providers  # noqa: F401 - registers the adapters in ADAPTERS
