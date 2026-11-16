# syntax=docker/dockerfile:1

# ---- Build stage: install the locked dependencies and the project with uv ----
FROM python:3.12-slim AS builder

# Pinned uv binary copied from the official image; no pip install of uv.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

# Compile bytecode once at build time, copy files instead of hard-linking out of the cache
# mount, and never download a Python: the base image already has 3.12.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first. This layer is rebuilt only when pyproject.toml or uv.lock change.
# --locked fails the build if uv.lock is out of date, so the image matches the lock file.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Then the project. hatchling needs README.md because pyproject.toml declares it as the readme.
# --no-editable installs a real copy into the virtual environment, so src/ is not needed later.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# ---- Runtime stage: only the virtual environment, no uv, no sources, no dev tools ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as a non-root user.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
USER app

EXPOSE 8000

# python is already in the image, so no curl is needed for the check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# One process on purpose: storage is in memory, so each extra worker would have its own
# separate data and its own lock (see README, limits). Revisit with PostgreSQL (feature 006).
CMD ["uvicorn", "disputes.main:app", "--host", "0.0.0.0", "--port", "8000"]
