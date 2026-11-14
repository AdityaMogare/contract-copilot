# Container image for the FastAPI app (design 02 §6). Built for linux/amd64, which ACA runs.
FROM python:3.12-slim

# uv from its official image: exact, reproducible installs from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Dependencies first (cached layer), app code second, so a code change doesn't reinstall deps.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

# Non-root: if the app is compromised, it can't modify the image's filesystem as root.
RUN useradd --uid 10001 --no-create-home appuser
USER 10001

EXPOSE 8000
CMD ["/srv/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
