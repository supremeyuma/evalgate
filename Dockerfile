FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md LICENSE alembic.ini ./
COPY src ./src
COPY examples ./examples
RUN uv sync --frozen --no-dev

COPY scripts/docker-entrypoint.sh /usr/local/bin/evalgate-entrypoint
RUN chmod +x /usr/local/bin/evalgate-entrypoint

ENTRYPOINT ["evalgate-entrypoint"]
CMD ["evalgate", "--help"]
