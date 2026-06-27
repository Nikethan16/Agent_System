"""Phase-1 reliability fixes: tool-name normalization, schema feedback, per-model
sampling, and the verification gate. All offline (a fake complete_chain)."""
import types

from core import toolbelt as tb
from core.registry import registry
from core import agent as A


# ---- 1.1 tool-name normalization -------------------------------------------
def test_tool_name_case_insensitive_and_alias():
    assert tb.get("write_file") is tb.get("Write_File")      # case-insensitive
    assert tb.get("WRITE_FILE") is tb.get("write_file")
    assert tb.get("read_file ") is tb.get("read_file")       # trimmed
    assert tb.get("bash") is tb.get("run_bash")              # alias
    assert tb.get("search") is tb.get("grep")                # alias
    assert tb.get("nope_not_a_tool") is None


# ---- 1.2 signature + unknown-arg detection ---------------------------------
def test_signature_and_unknown_args():
    wf = tb.get("write_file")
    sig = tb.signature(wf)
    assert "write_file(" in sig and "path" in sig
    assert tb.validate_args(wf, {}) is not None                       # missing required
    err = tb.validate_args(wf, {"path": "a.py", "content": "x", "fileContent": "y"})
    assert err and "unknown" in err.lower()                            # wrong key caught
    assert tb.validate_args(wf, {"path": "a.py", "content": "x"}) is None


# ---- 1.5 per-model sampling -------------------------------------------------
def test_sampling_for():
    s = registry.sampling_for("nvidia_nim/qwen/qwen3.5-122b-a10b")
    assert s.get("temperature") == 0.55 and s.get("repeat_penalty")
    assert registry.sampling_for("no/such/model") == {}


# ---- fakes for the verification-gate tests ---------------------------------
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
        return {"role": "assistant", "content": self.content}


def _resp(msg):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


# ---- 1.4 verification gate --------------------------------------------------
def test_verify_gate_labels_unverified_when_code_never_runs(monkeypatch):
    calls = {"n": 0}

    def fake_chain(models, messages, tools=None, **kw):
        calls["n"] += 1
        return _resp(_Msg("The answer is 42.")), 0.0      # never calls a tool

    monkeypatch.setattr(A, "complete_chain", fake_chain)
    out = A.run_agent("compute it", "sys", "m", verify_run=True, allowed_tools=["run_bash"])
    assert "UNVERIFIED" in out
    assert calls["n"] >= 3            # initial try + 2 forcing nudges before it gives up


def test_verify_gate_passes_when_code_runs(monkeypatch):
    seq = {"n": 0}

    def fake_chain(models, messages, tools=None, **kw):
        seq["n"] += 1
        if seq["n"] == 1:
            return _resp(_Msg("running it", [_TC("run_bash", '{"command": "python x.py"}')])), 0.0
        return _resp(_Msg("Done. The script printed OK.")), 0.0

    monkeypatch.setattr(A, "complete_chain", fake_chain)
    # Simulate a successful sandbox execution (no Docker locally) so ran_code is set.
    monkeypatch.setattr(A, "_run_one_tool",
                        lambda name, args, label, approve, emit: "exit=0\nOK" if name == "run_bash" else "ok")
    out = A.run_agent("build it", "sys", "m", verify_run=True, allowed_tools=["run_bash"])
    assert "UNVERIFIED" not in out
    assert "Done" in out


def test_verify_gate_off_by_default(monkeypatch):
    monkeypatch.setattr(A, "complete_chain",
                        lambda *a, **k: (_resp(_Msg("plain answer")), 0.0))
    out = A.run_agent("just answer", "sys", "m", allowed_tools=["run_bash"])
    assert "UNVERIFIED" not in out
