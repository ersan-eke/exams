# One image for the API and the worker; compose picks the command.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# dependencies in their own layer: they change far less often than the code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY . /app
ENV PATH="/app/.venv/bin:$PATH"

# non-root; uid 10001 must own the storage mount on the host
RUN useradd --uid 10001 --user-group --no-create-home app && mkdir -p /data/storage && chown app:app /data/storage
USER app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
