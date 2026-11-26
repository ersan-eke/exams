from contextlib import aclosing

import httpx
from google import genai
from google.genai import errors, types

from ..grader import ADAPTERS, OVERLOADED, Final, GradingError, Thinking
from ..models import LlmOut
from ..prompt import Image, Text


def _parts(items) -> list[types.Part]:
    # CacheBreak is Anthropic-only and dropped here
    return [
        types.Part(text=it.text) if isinstance(it, Text) else types.Part.from_bytes(data=it.png, mime_type="image/png")
        for it in items
        if isinstance(it, Text | Image)
    ]


def _code(e: errors.APIError) -> str:
    if e.code == 429:
        return "rate_limited"
    if e.code in OVERLOADED:
        return "overloaded"
    # Google answers a bad key with 400 API_KEY_INVALID
    if e.code in (401, 403) or "API_KEY_INVALID" in f"{e.details} {e.message}":
        return "bad_key"
    return "llm_failed"


async def stream(req, key, system, items, out=LlmOut):
    answer: list[str] = []
    client = genai.Client(api_key=key)
    try:
        s = await client.aio.models.generate_content_stream(
            model=req.model,
            contents=[types.Content(role="user", parts=_parts(items))],
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=out,
                thinking_config=types.ThinkingConfig(include_thoughts=True),
            ),
        )
        async with aclosing(s):
            async for chunk in s:
                if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                    raise GradingError("refused")
                for cand in chunk.candidates or []:
                    if cand.finish_reason == types.FinishReason.SAFETY:
                        raise GradingError("refused")
                    for p in (cand.content.parts or []) if cand.content else []:
                        if not p.text:
                            continue
                        if p.thought:
                            yield Thinking(p.text)
                        else:
                            answer.append(p.text)
    except errors.APIError as e:
        raise GradingError(_code(e)) from None
    except httpx.HTTPError:
        raise GradingError("llm_failed") from None
    finally:
        await client.aio.aclose()
    yield Final("".join(answer), req.model)


ADAPTERS["google"] = stream
