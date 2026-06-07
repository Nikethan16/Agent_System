# ---- stage 1: build the React frontend ----
FROM node:20-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# ---- stage 2: runtime (FastAPI serves the built app) ----
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ ./core/
COPY server/ ./server/
COPY tools/ ./tools/
COPY config/ ./config/
COPY evals/ ./evals/
COPY scripts/ ./scripts/
COPY skills/ ./skills/
COPY --from=web /web/dist ./web/dist

ENV DATA_DIR=/app/data
# Safe-by-default for a networked deployment: the cwd "sandbox" is NOT real
# containment, so disable the shell tool unless you run inside a hardened sandbox.
# Override with -e AGENT_DISABLE_BASH=0 only if you have real isolation.
ENV AGENT_DISABLE_BASH=1

# Run as a non-root user; give it ownership of the writable data dir.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data && chown -R appuser:appuser /app/data
USER appuser

EXPOSE 8000
# Provider keys + AGENT_AUTH_TOKEN come from the environment / .env at runtime
# (see docs/PLACEHOLDERS.md). Without AGENT_AUTH_TOKEN the API only serves loopback.
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
