# JobBot ready image: tool on PATH. Mount a host folder as the workspace.
#
#   docker build -t jobbot:local .
#   mkdir -p ~/postulaciones
#   docker compose run --rm -v "$HOME/postulaciones:/work" -w /work jobbot init
#
# HITL / headed logins still need your host browser — see docs/instalacion.md.

FROM python:3.12-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY templates ./templates
COPY data/profile.example.yaml data/portals.example.yaml ./data/

RUN uv sync --frozen --no-dev \
    && uv run playwright install --with-deps chromium \
    && uv build --wheel -o /dist \
    && rm -rf /var/lib/apt/lists/* /root/.cache/uv

# ── runtime: wheel only (no git tree) ────────────────────────────────────────
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/
COPY --from=build /dist /dist
COPY --from=build /ms-playwright /ms-playwright

ENV UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/root/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    && uv tool install --python 3.12 /dist/jobbot-*.whl \
    && rm -rf /var/lib/apt/lists/* /root/.cache/uv /dist

WORKDIR /work
ENTRYPOINT ["jobbot"]
CMD ["--help"]
