"""Regression tests for the human approval gate (Layer 3-4).

The bug (found 2026-07-12): when the security-manager's cheap model returned an empty /
garbled reply, `_manager_review` raised and the broker FAIL-CLOSED — denying the action and
never showing the human the Approve/Deny card. Under free-tier flakiness that silently broke
the entire human-in-the-loop gate. The fix: an '[infra]' manager failure is NOT a verdict, so
it falls through to the human (the real gate); only a GENUINE denial short-circuits.
"""
import threading
import time

import pytest

from core.toolbelt import Tool, RISK_WRITE
from core.policy import Decision
from server import approvals
from server.approvals import ApprovalBroker


def _tool():
    return Tool("run_bash", None, {"type": "object"}, RISK_WRITE, False)


def _decision():
    return Decision("escalate", "needs approval (require-human rule)", requires_human=True)


def test_infra_manager_failure_still_asks_the_human(monkeypatch):
    """A flaky manager (empty/garbled model reply) must NOT auto-deny — the human card
    must still appear so the person can decide."""
    monkeypatch.setattr(approvals, "_manager_review",
                        lambda *a, **k: (False, "[infra] manager unavailable: JSONDecodeError"))
    events = []
    broker = ApprovalBroker(emit=events.append, mode="auto", session_id="s", run_id="r")

    out = {}

    def run():
        out["ret"] = broker.approve(_tool(), {"command": "bash deploy.sh"}, _decision())

    t = threading.Thread(target=run)
    t.start()

    req = None
    for _ in range(200):                       # wait up to ~4s for the human card
        req = next((e for e in events if e.get("type") == "approval_request"), None)
        if req:
            break
        time.sleep(0.02)
    assert req is not None, "human approval card was never requested (fail-closed regression)"

    approvals.resolve(req["id"], True, "approved by human")   # the human clicks Approve
    t.join(timeout=5)
    assert out["ret"][0] is True               # the action is allowed once the human approves


def test_genuine_manager_denial_blocks_without_asking_human(monkeypatch):
    """A real manager verdict of 'deny' still blocks immediately — and does NOT bother the human."""
    monkeypatch.setattr(approvals, "_manager_review",
                        lambda *a, **k: (False, "unsafe: destroys data"))
    events = []
    broker = ApprovalBroker(emit=events.append, mode="auto", session_id="s", run_id="r")

    allowed, reason = broker.approve(_tool(), {"command": "rm -rf /important"}, _decision())
    assert allowed is False
    assert "manager denied" in reason
    assert not any(e.get("type") == "approval_request" for e in events)


def test_trusted_mode_auto_approves(monkeypatch):
    """Sanity: trusted mode never consults the manager or the human."""
    called = {"mgr": False}

    def _mgr(*a, **k):
        called["mgr"] = True
        return (True, "ok")

    monkeypatch.setattr(approvals, "_manager_review", _mgr)
    broker = ApprovalBroker(emit=lambda e: None, mode="trusted")
    allowed, _ = broker.approve(_tool(), {"command": "anything"}, _decision())
    assert allowed is True
    assert called["mgr"] is False
