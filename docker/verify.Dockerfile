# Preloaded verification sandbox image for run_bash.
#
# WHY THIS EXISTS: the default run_bash sandbox runs with --network none (no egress),
# which is the right security posture — but it means the agent can't `pip install` /
# `npm install` at runtime, so it can't actually run pytest / a test suite for any
# project with dependencies. Rather than open the network (AGENT_BASH_DOCKER_NETWORK=
# bridge), we bake the common test tooling into the image so the verify loop runs
# OFFLINE. The container still has no credentials, drops all caps, and is read-only
# except the mounted workspace + /tmp.
#
# Build (tags agent-verify:latest):   ./docker/build-verify-image.sh
# Then in .env:  AGENT_BASH_DOCKER_IMAGE=agent-verify:latest
#
# Add a dependency your projects commonly need by appending to the pip/npm lines
# below and rebuilding — that keeps network=none viable. For the rare project that
# needs a fresh install, set AGENT_BASH_DOCKER_NETWORK=bridge for that run instead.
FROM python:3.11-slim

# Node.js (for npm/JS verification) + git, kept minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Common Python test/build tooling, baked in so `network=none` can still run a suite.
RUN pip install --no-cache-dir \
        pytest pytest-cov \
        requests httpx \
        numpy pandas \
        pydantic \
        fastapi uvicorn \
        flask \
        rich

# Document-generation libraries — the Anthropic doc skills (docx/xlsx/pptx/pdf) run
# generator scripts inside this sandbox, and `--network none` blocks installing them at
# runtime, so bake them in. Without these, "create a real .xlsx/.docx/.pdf" produces no
# file (the agent burns its iteration budget on a failing `pip install`).
RUN pip install --no-cache-dir \
        openpyxl xlsxwriter \
        python-docx \
        python-pptx \
        reportlab pypdf pdfplumber \
        markitdown \
        Pillow \
        lxml defusedxml

# A couple of widely-used JS test runners, global so they resolve offline.
RUN npm install -g --no-audit --no-fund vitest jest 2>/dev/null || true

WORKDIR /ws
CMD ["bash"]
