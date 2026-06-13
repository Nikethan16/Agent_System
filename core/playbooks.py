"""
playbooks.py — task PLAYBOOKS: the proven path each task type follows.

Config-driven (config/playbooks.yaml). The orchestrator seeds the LEAD with a playbook's
phases (goal + preferred agent + gate) so substantive work is predictable and the right
specialist is pulled per phase. ANY task type not in the config uses `default` — the
BACKUP PATH — so every task is covered. Stays in core/ (offline, no model/provider/UI).
"""
import os
import threading

import yaml

_PATH = os.environ.get(
    "PLAYBOOKS_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config", "playbooks.yaml"))

# Map router task_types (and a few synonyms) onto the playbook keys; anything else
# resolves to `default`.
_ALIASES = {"math": "data", "analysis": "data", "finance": "data", "csv": "data",
            "general": "default", "chat": "default", "unknown": "default", "qa": "default"}


class Playbooks:
    def __init__(self, path: str = _PATH):
        self.path = path
        self._lock = threading.Lock()
        self.reload()

    def reload(self):
        try:
            with open(self.path) as f:
                self.cfg = (yaml.safe_load(f) or {}).get("playbooks", {}) or {}
        except Exception:
            self.cfg = {}

    def select(self, task_type: str) -> list:
        """The ordered phases for a task type, falling back to `default` (backup path)."""
        tt = (task_type or "").strip().lower()
        key = tt if tt in self.cfg else _ALIASES.get(tt, "default")
        return self.cfg.get(key) or self.cfg.get("default") or []


playbooks = Playbooks()


def select(task_type: str) -> list:
    return playbooks.select(task_type)


def as_todos(phases: list) -> list:
    """Playbook phases -> the LEAD's initial todo list."""
    return [{"text": f"{p.get('phase', 'step')}: {p.get('goal', '')}", "status": "pending"}
            for p in (phases or [])]


def guidance(phases: list) -> str:
    """The playbook rendered for the LEAD's system prompt — phase, preferred agent, gate."""
    if not phases:
        return ""
    lines = ["PLAYBOOK — follow this path. Advance to the next phase only when the current "
             "phase's [gate] is met. Prefer the listed specialist for each phase (delegate to "
             "it), but use a better-fit agent if the task clearly needs one, and skip a phase "
             "that genuinely doesn't apply:"]
    for i, p in enumerate(phases, 1):
        a = f"  → delegate to: {p['agent']}" if p.get("agent") else ""
        g = f"  [gate: {p['gate']}]" if p.get("gate") else ""
        lines.append(f"{i}. {p.get('phase', 'step')}: {p.get('goal', '')}{a}{g}")
    return "\n".join(lines)


def checklist(task_type: str) -> str:
    """A compact one-line path for a single (tier-2) agent to follow in its own loop."""
    phases = select(task_type)
    if not phases:
        return ""
    return "Approach: " + " → ".join(p.get("phase", "step") for p in phases) + "."
