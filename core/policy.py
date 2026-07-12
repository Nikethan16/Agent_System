"""
policy.py — the deterministic security gate (Layer 2) + the append-only audit log.

Offline, no model calls — just fast pattern rules from config/policy.yaml. Every tool
call is evaluated here BEFORE it runs. Escalations (critical tools, or content that
matches the rules) are handed to the caller's approval flow (manager agent + human),
which lives outside core. Every decision is appended to the audit log.
"""
import os
import re
import json
import time
import threading

import yaml

from .toolbelt import Tool, RISK_SAFE, RISK_WRITE, RISK_CRITICAL

_CFG_PATH = os.environ.get(
    "POLICY_CONFIG",
    os.path.join(os.path.dirname(__file__), "..", "config", "policy.yaml"),
)
_AUDIT_PATH = os.environ.get(
    "AUDIT_LOG",
    os.path.join(os.path.dirname(__file__), "..", "audit.log"),
)

_lock = threading.Lock()


class Decision:
    def __init__(self, action: str, reason: str, requires_human: bool = False):
        # action ∈ {"allow", "escalate", "block"}
        self.action = action
        self.reason = reason
        self.requires_human = requires_human

    @property
    def allowed(self) -> bool:
        return self.action == "allow"

    def __repr__(self):
        return f"Decision({self.action}, human={self.requires_human}, {self.reason!r})"


def _load():
    try:
        with open(_CFG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}
    return (
        [re.compile(p, re.I) for p in cfg.get("hard_block", [])],
        [re.compile(p, re.I) for p in cfg.get("require_human", [])],
    )


_HARD_BLOCK, _REQUIRE_HUMAN = _load()

# Read-only shell commands are safe to run without escalation/approval (mirrors how
# Claude Code lets `ls`/`cat`/etc. run in every mode). Only a bare, single command from
# this allowlist with NO shell metacharacters qualifies — anything with pipes,
# redirects, chaining, or substitution still goes through the normal gate.
_SAFE_BASH = re.compile(r"^\s*(ls|cat|pwd|head|tail|wc|echo|find|grep|stat|file|tree|which)\b")
_UNSAFE_SHELL = re.compile(r"[;&|`><]|\$\(|\$\{")


def _is_readonly_bash(args: dict) -> bool:
    cmd = (args.get("command") or "") if isinstance(args, dict) else ""
    if not cmd or _UNSAFE_SHELL.search(cmd):
        return False
    return bool(_SAFE_BASH.match(cmd))


# File-data payload fields: the CONTENT an agent writes, not an action it takes. The
# policy patterns describe ACTIONS (shell commands, DB ops, deploys) — so a document
# that merely mentions "deploy", or code that contains the literal "delete from" in a
# query builder, must NOT trip an action rule and get a benign write escalated/denied.
# If that content is ever executed, the run_bash that runs it is gated on its own.
_PAYLOAD_KEYS = {"content", "new_string", "old_string", "patch", "text", "body"}


def _scan_blob(args: dict) -> str:
    """Stringify args for pattern matching, EXCLUDING file-data payload fields."""
    if isinstance(args, dict):
        args = {k: v for k, v in args.items() if k not in _PAYLOAD_KEYS}
    return json.dumps(args, default=str).lower()


def reload():
    global _HARD_BLOCK, _REQUIRE_HUMAN
    _HARD_BLOCK, _REQUIRE_HUMAN = _load()


def evaluate(tool: Tool, args: dict) -> Decision:
    """Decide what gating a tool call needs, deterministically."""
    blob = _scan_blob(args)

    for pat in _HARD_BLOCK:
        if pat.search(blob):
            return Decision("block", f"blocked by policy: matches /{pat.pattern}/")

    human_by_content = any(pat.search(blob) for pat in _REQUIRE_HUMAN)
    requires_human = bool(tool.requires_human or human_by_content)

    # A safe, bare read-only shell command auto-allows even if run_bash is otherwise
    # gated (e.g. no Docker -> CRITICAL) — as long as no require-human rule matched it.
    if tool.name == "run_bash" and not human_by_content and _is_readonly_bash(args):
        return Decision("allow", "read-only shell command")

    if tool.risk == RISK_CRITICAL or requires_human:
        why = "critical tool" if tool.risk == RISK_CRITICAL else "matches require-human rule"
        return Decision("escalate", f"needs approval ({why})", requires_human=requires_human)

    # safe / write with no dangerous content
    return Decision("allow", f"{tool.risk} action allowed")


def audit(record: dict) -> None:
    """Append-only audit log (one JSON object per line)."""
    record = {"ts": time.time(), **record}
    line = json.dumps(record, default=str)
    with _lock:
        d = os.path.dirname(_AUDIT_PATH)
        if d:
            os.makedirs(d, exist_ok=True)   # never crash a tool call on a missing log dir
        # G6: rotate when the log gets big so it can't grow without bound (keep one .1).
        try:
            cap = int(os.environ.get("AUDIT_LOG_MAX_BYTES", "5000000"))
            if os.path.exists(_AUDIT_PATH) and os.path.getsize(_AUDIT_PATH) > cap:
                os.replace(_AUDIT_PATH, _AUDIT_PATH + ".1")
        except OSError:
            pass
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
