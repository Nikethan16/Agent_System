"""Unit tests for server/trace.py — build_tree() and load_trace()."""
import json
import os
import tempfile

import pytest


# Patch _DIR before importing so we write into a temp directory.
import server.trace as tr


def _write_events(session_id: str, events: list, tmpdir: str):
    path = os.path.join(tmpdir, f"{session_id}.jsonl")
    with open(path, "w") as f:
        for i, ev in enumerate(events):
            f.write(json.dumps({"ts": 1000.0 + i, "session_id": session_id, **ev}) + "\n")


@pytest.fixture(autouse=True)
def patch_trace_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_DIR", str(tmp_path))


SID = "a" * 32


class TestLoadTrace:
    def test_returns_empty_for_missing_session(self):
        assert tr.load_trace(SID) == []

    def test_parses_events_oldest_first(self, tmp_path):
        _write_events(SID, [{"type": "route"}, {"type": "assign", "agent": "x"}], str(tmp_path))
        evs = tr.load_trace(SID)
        assert len(evs) == 2
        assert evs[0]["type"] == "route"
        assert evs[1]["type"] == "assign"

    def test_tolerates_malformed_line(self, tmp_path):
        path = os.path.join(str(tmp_path), f"{SID}.jsonl")
        with open(path, "w") as f:
            f.write('{"ts":1,"type":"route","session_id":"' + SID + '"}\n')
            f.write("NOT JSON\n")
            f.write('{"ts":2,"type":"plan","session_id":"' + SID + '"}\n')
        evs = tr.load_trace(SID)
        assert len(evs) == 2
        assert evs[1]["type"] == "plan"


class TestBuildTree:
    def _tree(self, events):
        _write_events(SID, events, tr._DIR)
        return tr.build_tree(SID)

    def test_empty_trace(self):
        result = self._tree([])
        assert result["root"]["name"] == "agent-run"
        assert result["root"]["children"] == []
        assert result["totals"] == {"cost": 0.0, "tokens": 0, "duration_ms": None}

    def test_single_agent_span(self):
        result = self._tree([
            {"type": "assign", "agent": "coder", "subtask": "write code"},
            {"type": "done", "cost": 0.01, "tokens": 100},
        ])
        children = result["root"]["children"]
        assert len(children) == 1
        assert children[0]["name"] == "agent:coder"
        assert children[0]["kind"] == "agent"
        assert children[0]["cost"] == pytest.approx(0.01)
        assert children[0]["tokens"] == 100

    def test_tool_nested_inside_agent(self):
        result = self._tree([
            {"type": "assign", "agent": "coder"},
            {"type": "tool", "name": "write_file", "args": {"path": "a.py"}, "tokens": 20},
            {"type": "done"},
        ])
        agent = result["root"]["children"][0]
        assert len(agent["children"]) == 1
        assert agent["children"][0]["name"] == "tool:write_file"
        assert agent["children"][0]["kind"] == "tool"

    def test_run_complete_sets_root_totals(self):
        result = self._tree([
            {"type": "route", "tier": 3},
            {"type": "assign", "agent": "coder"},
            {"type": "done"},
            {"type": "run_complete", "cost": 0.05, "tokens": 500, "iterations": 2},
        ])
        assert result["totals"]["cost"] == pytest.approx(0.05)
        assert result["totals"]["tokens"] == 500

    def test_duration_computed_from_ts(self):
        result = self._tree([
            {"type": "assign", "agent": "a"},  # ts=1000.0
            {"type": "done"},                   # ts=1001.0
        ])
        agent = result["root"]["children"][0]
        assert agent["duration_ms"] == pytest.approx(1000)

    def test_nested_delegation(self):
        """Lead → coder → (tool inside coder)."""
        result = self._tree([
            {"type": "assign", "agent": "lead"},
            {"type": "assign", "agent": "coder"},
            {"type": "tool", "name": "read_file"},
            {"type": "done"},   # coder done
            {"type": "done"},   # lead done
        ])
        lead = result["root"]["children"][0]
        assert lead["name"] == "agent:lead"
        coder = lead["children"][0]
        assert coder["name"] == "agent:coder"
        assert coder["children"][0]["name"] == "tool:read_file"

    def test_unclosed_span_gets_last_ts(self):
        """A crashed run leaves open spans — they should get the last known ts."""
        result = self._tree([
            {"type": "assign", "agent": "coder"},  # never closed
            {"type": "tool", "name": "write_file"},
        ])
        agent = result["root"]["children"][0]
        # end is set to last ts, so duration_ms is not None
        assert agent["duration_ms"] is not None
