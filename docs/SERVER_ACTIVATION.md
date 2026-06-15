# Server activation runbook — 2026-06-15 features

The repo-mode / Docker-sandbox / Langfuse-tracing features shipped on 2026-06-15 are
**code-complete but dormant on the production VM** because they need server-side env +
infra that the agent cannot set (server `.env` is gitignored and a safety classifier
blocks the agent from writing server secrets). This is the **owner checklist** to turn
them on over SSH. Do it once; CI/CD does not touch `.env`.

> Target: Oracle ARM VM, user `ubuntu`, app at `/home/ubuntu/agent_system`, systemd
> service `agentcore`. Reach it via Tailscale (`ssh ubuntu@100.89.151.102`).

## 1. Build an ARM64 sandbox image
`run_bash` executes inside a hardened `docker run` (`--cap-drop ALL`, `--read-only`,
`--no-new-privileges`, pids/mem/cpu caps — see `core/tools.py:194`). It needs a local
image with `bash` (+ whatever toolchains repo-mode tasks require: `git`, `python3`,
`node`, etc.). Build one on the VM, e.g.:

```bash
# on the VM
cat > /tmp/sandbox.Dockerfile <<'EOF'
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash git ca-certificates curl python3 python3-pip nodejs npm \
 && rm -rf /var/lib/apt/lists/*
EOF
docker build -t agent-sandbox:arm64 -f /tmp/sandbox.Dockerfile /tmp
```

## 2. Set the env vars (server `.env`, owner-only)
Edit `/home/ubuntu/agent_system/.env`:

```bash
AGENT_BASH_DOCKER_IMAGE=agent-sandbox:arm64   # enables run_bash; makes it RISK_WRITE (no human click)
AGENT_BASH_DOCKER_NETWORK=bridge              # needed for git clone + pip/npm installs (default is "none")
# remove or set to 0 — it currently disables the shell entirely:
# AGENT_DISABLE_BASH=1     ← delete this line
GITHUB_TOKEN=ghp_xxx                          # repo-mode clone/push + create_pull_request (tools/github.py)
```

Optional tracing (Langfuse span tree, surfaced by the new Trace panel only needs the
local JSONL — Langfuse is for the hosted UI):

```bash
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com   # or self-hosted
```

```bash
# if enabling Langfuse, install the SDK into the service venv:
cd /home/ubuntu/agent_system && .venv/bin/pip install langfuse
```

Other knobs (have safe defaults, override only if needed): `AGENT_BASH_DOCKER_TIMEOUT`
(120s), `AGENT_BASH_DOCKER_MEMORY` (512m), `AGENT_BASH_DOCKER_CPUS` (1.0),
`AGENT_BASH_DOCKER_PIDS` (64).

## 3. Restart + verify
```bash
sudo systemctl restart agentcore
sudo systemctl status agentcore --no-pager
docker images | grep agent-sandbox        # image present
docker ps                                  # nothing stuck running
```

## 4. End-to-end repo-mode smoke test
From the UI (Tailscale `http://100.89.151.102:8800`), run a repo task, e.g.:
> "Clone <a small repo you own>, add a one-line note to its README, commit on a branch, and open a PR."

Confirm:
- the **repo-engineer** agent / **repo** playbook is selected;
- `run_bash` runs (Docker sandbox) without a human-approval prompt for safe commands;
- clone + `pip`/`npm` succeed (network = bridge);
- **push** and **create_pull_request** correctly require human approval;
- the new **Trace** panel shows the run's span tree (and Langfuse, if configured).

## Notes
- The sandbox is fail-closed: with no `AGENT_BASH_DOCKER_IMAGE`, `run_bash` returns an
  error instead of falling back to the host shell (`core/tools.py:177`).
- `bridge` networking is required for clones/installs; tighten back to `none` for tasks
  that don't need the network if you want maximum isolation.
- Keep `GITHUB_TOKEN` scoped to the repos you actually want the agent to touch.
