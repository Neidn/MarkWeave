FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_TOOL_BIN_DIR=/usr/local/bin

RUN pip install --no-cache-dir uv

# graphify reads the graph this server queries. The version is pinned to the
# one that BUILDS graph.json on the host — a mismatch can break reads silently.
ARG GRAPHIFY_VERSION=0.9.35
RUN uv tool install "graphifyy==${GRAPHIFY_VERSION}"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    MARKWEAVE_VAULT=/vault \
    MARKWEAVE_GRAPH=/vault/graphify-out/graph.json \
    MARKWEAVE_GRAPHIFY_BIN=/usr/local/bin/graphify \
    MARKWEAVE_HOST=0.0.0.0 \
    MARKWEAVE_PORT=8000

EXPOSE 8000

CMD ["markweave-mcp"]
