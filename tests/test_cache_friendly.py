"""Cache-friendliness guarantee.

Prompt caching (DeepSeek ~98% off cache-hit input, ~90% hit rate in agentic loops)
only fires when consecutive model calls share a STABLE PREFIX: the system message and
the earlier turns must be byte-identical from one call to the next, with new content
appended only at the END. This test locks that property into the agent loop — if a
future change mutates the system prompt between turns or inserts into the prefix, the
cache silently stops hitting and cost jumps. That regression should fail a test, loudly.
"""
import types

from core import agent as A


class _Fn:
    def __init__(self, name, args):
        self.name, self.arguments = name, args


class _TC:
    def __init__(self, name, args):
        self.id, self.function = "t1", _Fn(name, args)


class _Msg:
    def __init__(self, content, tcs=None):
        self.content, self.tool_calls = content, tcs

    def model_dump(self):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in self.tool_calls]
        return d


def _resp(msg):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def _run_capturing(monkeypatch, script):
    """Drive run_agent, snapshotting the FULL message list passed to the model on every
    call. `script` yields the assistant message to return for call N (1-indexed)."""
    snapshots = []

    def fake_chain(models, messages, tools=None, **kw):
        # Deep-ish copy of the prefix-relevant fields so later appends don't mutate the snap.
        snapshots.append([dict(m) for m in messages])
        n = len(snapshots)
        return _resp(script(n)), 0.0

    monkeypatch.setenv("AGENT_COMPACT", "0")     # compaction deliberately rewrites the
    #                                              middle on huge histories (a rare, accepted
    #                                              cache reset) — exclude it from this check.
    monkeypatch.setattr(A, "complete_chain", fake_chain)
    monkeypatch.setattr(A, "_run_one_tool",
                        lambda name, args, label, approve, emit: "exit=0\nOK")
    A.run_agent("do the task", "STABLE SYSTEM PROMPT", "m",
                allowed_tools=["run_bash", "read_file"])
    return snapshots


def _script(n):
    # Two tool rounds, then a final answer — a realistic multi-turn loop.
    if n == 1:
        return _Msg("step 1", [_TC("read_file", '{"path": "a.py"}')])
    if n == 2:
        return _Msg("step 2", [_TC("run_bash", '{"command": "pytest"}')])
    return _Msg("all done")


def test_system_message_is_stable_across_turns(monkeypatch):
    snaps = _run_capturing(monkeypatch, _script)
    assert len(snaps) >= 3
    system0 = snaps[0][0]
    for s in snaps:
        assert s[0]["role"] == "system"
        assert s[0] == system0, "system prompt changed between turns — breaks prompt cache"


def test_initial_task_message_is_stable(monkeypatch):
    snaps = _run_capturing(monkeypatch, _script)
    task0 = snaps[0][1]
    for s in snaps:
        assert s[1] == task0, "initial task message changed between turns — breaks cache"


def test_each_call_is_a_prefix_extension(monkeypatch):
    """The core cache property: call N's messages must equal call N+1's messages[:N_len]
    — i.e. the loop only ever APPENDS; it never edits or reorders earlier messages."""
    snaps = _run_capturing(monkeypatch, _script)
    for prev, cur in zip(snaps, snaps[1:]):
        assert len(cur) > len(prev), "history did not grow — unexpected"
        assert cur[:len(prev)] == prev, (
            "an earlier message changed between turns — the stable prefix broke, "
            "so the provider's prompt cache will miss and cost will spike")
