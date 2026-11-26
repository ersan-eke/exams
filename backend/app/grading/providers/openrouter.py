import base64

import openai
from openai import AsyncOpenAI

from ..grader import ADAPTERS, OVERLOADED, Final, GradingError
from ..models import LlmOut, llm_schema
from ..prompt import Image, Text


def _content(items) -> list[dict]:
    # CacheBreak is Anthropic-only and dropped here
    return [
        {"type": "text", "text": it.text}
        if isinstance(it, Text)
        else {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(it.png).decode()}}
        for it in items
        if isinstance(it, Text | Image)
    ]


# shortcut: no Thinking events, since reasoning deltas are non-standard on OpenRouter; stream `delta.reasoning` once a model needs it
async def stream(req, key, system, items, out=LlmOut):
    answer: list[str] = []
    model = None
    try:
        async with AsyncOpenAI(api_key=key, base_url="https://openrouter.ai/api/v1") as client:
            s = await client.chat.completions.create(
                model=req.model,
                stream=True,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": _content(items)}],
                response_format={"type": "json_schema", "json_schema": {"name": "grade", "strict": True, "schema": llm_schema(out)}},
                extra_body={"provider": {"require_parameters": True}},  # else OpenRouter may route to a host that ignores the schema
            )
            async with s:
                async for chunk in s:
                    model = chunk.model or model
                    if not chunk.choices:
                        continue
                    if chunk.choices[0].delta.content:
                        answer.append(chunk.choices[0].delta.content)
                    if chunk.choices[0].finish_reason == "content_filter":
                        raise GradingError("refused")
    except openai.AuthenticationError:
        raise GradingError("bad_key") from None
    except openai.RateLimitError:
        raise GradingError("rate_limited") from None
    except openai.APIStatusError as e:
        code = "no_credits" if e.status_code == 402 else "overloaded" if e.status_code in OVERLOADED else "llm_failed"
        raise GradingError(code) from None
    except openai.APIConnectionError:
        raise GradingError("llm_failed") from None
    yield Final("".join(answer), model)


ADAPTERS["openrouter"] = stream
