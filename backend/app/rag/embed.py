"""Local sentence embeddings (ONNX, no API key). The worker and the API both call this; tests replace `embed` with a fake."""

from functools import cache

from fastembed import TextEmbedding

# shortcut: model is fixed and `chunks.embedding` is vector(384); a different model needs a re-embed migration.
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@cache
def _model() -> TextEmbedding:
    return TextEmbedding(MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts)]
