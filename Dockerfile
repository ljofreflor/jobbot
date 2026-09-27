# Jobbot ready image: Python 3.12 + uv + Playwright Chromium.
# Build:  docker build -t jobbot:local .
# Run:    docker compose run --rm jobbot version
#
# HITL / headed portal logins (Indeed, LinkedIn, CAPTCHA) still need your
# host browser and usually a residential IP — see docs/instalacion.md.

FROM python:3.12-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# System libs Playwright Chromium needs (also pulled by install-deps below).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dependency metadata first for layer caching.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY templates ./templates
COPY data/profile.example.yaml data/portals.example.yaml ./data/

RUN uv sync --frozen --no-dev \
    && uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache/uv

# Runtime dirs mounted by compose; keep empty placeholders in the image.
RUN mkdir -p /app/output /app/browser-data \
    && cp data/profile.example.yaml data/profile.yaml

ENV PATH="/app/.venv/bin:${PATH}"

ENTRYPOINT ["uv", "run", "jobbot"]
CMD ["--help"]
