import base64

import anthropic
from anthropic import AsyncAnthropic

from ..grader import ADAPTERS, OVERLOADED, Final, GradingError, Thinking
from ..models import LlmOut, llm_schema
from ..prompt import CacheBreak, Image, Text


def _blocks(items) -> list[dict]:
    blocks: list[dict] = []
    for it in items:
        if isinstance(it, Text):
            blocks.append({"type": "text", "text": it.text})
        elif isinstance(it, Image):
            data = base64.b64encode(it.png).decode()
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
        elif isinstance(it, CacheBreak) and blocks:
            blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


async def stream(req, key, system, items, out=LlmOut):
    extra = {"fallbacks": "default", "betas": ["server-side-fallback-2026-07-01"]} if "sonnet" in req.model else {}
    try:
        async with (
            AsyncAnthropic(api_key=key) as client,
            client.beta.messages.stream(
                model=req.model,
                max_tokens=16000,
                system=[{"type": "text", "text": system}],
                messages=[{"role": "user", "content": _blocks(items)}],
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"format": {"type": "json_schema", "schema": llm_schema(out)}},
                **extra,
            ) as s,
        ):
            async for ev in s:
                if ev.type == "content_block_delta" and ev.delta.type == "thinking_delta":
                    yield Thinking(ev.delta.thinking)
            msg = await s.get_final_message()
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise GradingError("bad_key") from None
    except anthropic.RateLimitError:
        raise GradingError("rate_limited") from None
    except anthropic.APIStatusError as e:
        code = "no_credits" if e.status_code == 402 else "overloaded" if e.status_code in OVERLOADED else "llm_failed"
        raise GradingError(code) from None
    except anthropic.APIConnectionError:
        raise GradingError("llm_failed") from None
    if msg.stop_reason == "refusal":
        raise GradingError("refused")
    yield Final("".join(b.text for b in msg.content if b.type == "text"), msg.model)


ADAPTERS["anthropic"] = stream
