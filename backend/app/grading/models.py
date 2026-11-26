"""Request/response contract of LLM grading, shared by the route and all provider adapters."""

import base64
import re
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

MAX_IMAGES = 20
MAX_IMAGE_CHARS = 4_000_000
MAX_TEXT = 20_000


def _png(v: str) -> str:
    try:
        ok = base64.b64decode(v, validate=True).startswith(b"\x89PNG")
    except ValueError:
        ok = False
    if not ok:
        raise ValueError("not a base64 PNG")
    return v


Png = Annotated[str, Field(max_length=MAX_IMAGE_CHARS), AfterValidator(_png)]
Text = Annotated[str, Field(max_length=MAX_TEXT)]


class Part(BaseModel):
    text: Text = ""
    images: list[Png] = []


class RubricLine(BaseModel):
    item: Text
    max: float
    source: Literal["solution", "inferred"]


class Solution(Part):
    rubric: list[RubricLine] = []


class Reference(BaseModel):
    question: Part
    solution: Solution
    points: float


Provider = Literal["anthropic", "google", "openrouter"]
MODELS: dict[str, tuple[str, ...]] = {
    "anthropic": ("claude-sonnet-5-5", "claude-haiku-5-5"),
    "google": ("gemini-flash-latest", "gemini-pro-latest"),
}
DEFAULT_MODEL: dict[Provider, str] = {
    "anthropic": "claude-sonnet-5-5",
    "google": "gemini-flash-latest",
    "openrouter": "google/gemini-2.5-flash",
}
_OPENROUTER_ID = re.compile(r"[\w.\-]+/[\w.\-:]+", re.ASCII)


def resolve_model(provider: Provider, model: str | None) -> str:
    """The default model, or `model` when it is allowed for the provider (OpenRouter: any well-formed id)."""
    model = model or DEFAULT_MODEL[provider]
    if provider == "openrouter":
        if len(model) > 100 or not _OPENROUTER_ID.fullmatch(model):
            raise ValueError("bad model id")
    elif model not in MODELS[provider]:
        raise ValueError("model not allowed")
    return model


class GradeIn(BaseModel):
    provider: Provider = "anthropic"
    model: str | None = None
    points: float = Field(gt=0, le=1000)
    question: Part
    solution: Solution | None = None
    references: list[Reference] = Field(default=[], max_length=3)
    answer: Part
    subject: str | None = Field(None, max_length=100)  # lets a signed-in caller's course material be added when there is no solution
    exclude_exams: list[uuid.UUID] = Field(default=[], max_length=10)  # the exam being graded and its solution exam: left out of the material
    material: Text = ""  # filled in by the route from the caller's own material, never trusted from the body

    @model_validator(mode="after")
    def _check(self):
        self.model = resolve_model(self.provider, self.model)
        parts = [self.question, self.answer, *([self.solution] if self.solution else [])]
        parts += [p for r in self.references for p in (r.question, r.solution)]
        if sum(len(p.images) for p in parts) > MAX_IMAGES:
            raise ValueError(f"more than {MAX_IMAGES} images")
        return self


class LlmLine(BaseModel):
    item: str
    max: float
    hit: float
    note: str
    source: Literal["solution", "inferred"]


class LlmOut(BaseModel):
    points: float
    points_min: float
    points_max: float
    rubric: list[LlmLine]
    feedback: str


class GradeOut(LlmOut):
    certain: bool
    basis: Literal["solution", "own_solution"]
    provider: Provider
    model: str


def llm_schema(model: type[BaseModel] = LlmOut) -> dict:
    """`model` (the grade by default) as a strict JSON schema (refs inlined, no extra keys, all required) that all three providers accept."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(n):
        if isinstance(n, list):
            return [walk(x) for x in n]
        if not isinstance(n, dict):
            return n
        if "$ref" in n:
            return walk(defs[n["$ref"].rsplit("/", 1)[1]])
        n = {k: walk(v) for k, v in n.items() if k not in ("title", "default")}
        if n.get("type") == "object":
            n["additionalProperties"] = False
            n["required"] = list(n["properties"])
        return n

    return walk(schema)
