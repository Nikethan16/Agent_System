"""Tests for Fusion (panel-of-models + judge synthesis). Fully offline: `complete` /
`complete_chain` are stubbed, so no provider keys or network are needed."""
import time
import types

import pytest

from core import fusion


def _resp(text):
    """A minimal stand-in for (ModelResponse, cost) — resp.choices[0].message.content."""
    choice = types.SimpleNamespace(message=types.SimpleNamespace(content=text))
    return types.SimpleNamespace(choices=[choice]), 0.0


def test_fuse_synthesizes_and_anonymizes(monkeypatch):
    answers = {"m1": "Aye", "m2": "Bee", "m3": "Cee"}
    seen = {}

    def fake_complete(model, messages, **kw):
        if messages and messages[0].get("role") == "system":      # the judge call
            seen["judge_user"] = messages[1]["content"]
            return _resp("FINAL ANSWER")
        return _resp(answers[model])

    monkeypatch.setattr(fusion, "complete", fake_complete)
    out = fusion.fuse("What?", ["m1", "m2", "m3"], judge_model="J",
                      min_panel=3, grace_s=2.0, hard_timeout_s=5)
    assert out == "FINAL ANSWER"
    j = seen["judge_user"]
    assert "Source 1" in j and "Source 3" in j                    # anonymized labels present
    assert "Aye" in j and "Bee" in j and "Cee" in j               # every answer handed to judge
    for mid in ("m1", "m2", "m3"):
        assert mid not in j                                       # model ids never leak to judge


def test_quorum_grace_skips_straggler(monkeypatch):
    def fake_complete(model, messages, **kw):
        if messages[0].get("role") == "system":
            return _resp("FUSED")
        if model == "slow":
            time.sleep(1.5)                                       # slower than the grace window
        return _resp("ok-" + model)

    monkeypatch.setattr(fusion, "complete", fake_complete)
    t = time.time()
    out = fusion.fuse("Q", ["fast1", "fast2", "slow"], judge_model="J",
                      min_panel=2, grace_s=0.2, hard_timeout_s=10)
    assert out == "FUSED"
    assert time.time() - t < 1.2                                  # didn't wait for the 1.5s member


def test_single_answer_returned_without_judge(monkeypatch):
    judged = {"called": False}

    def fake_complete(model, messages, **kw):
        if messages[0].get("role") == "system":
            judged["called"] = True
            return _resp("SHOULD-NOT-HAPPEN")
        if model == "ok":
            return _resp("solo answer")
        raise RuntimeError("down")

    monkeypatch.setattr(fusion, "complete", fake_complete)
    out = fusion.fuse("Q", ["ok", "down1", "down2"], judge_model="J",
                      min_panel=2, grace_s=0.2, hard_timeout_s=3)
    assert out == "solo answer" and judged["called"] is False     # nothing to fuse -> no judge


def test_no_answers_raises(monkeypatch):
    def fake_complete(model, messages, **kw):
        if messages[0].get("role") == "system":
            return _resp("x")
        raise RuntimeError("down")

    monkeypatch.setattr(fusion, "complete", fake_complete)
    with pytest.raises(RuntimeError):
        fusion.fuse("Q", ["a", "b"], judge_model="J", min_panel=2, hard_timeout_s=2)


def test_dedup_panel(monkeypatch):
    seen = []

    def fake_complete(model, messages, **kw):
        if messages[0].get("role") == "system":
            return _resp("F")
        seen.append(model)
        return _resp("a")

    monkeypatch.setattr(fusion, "complete", fake_complete)
    fusion.fuse("Q", ["a", "a", "b"], judge_model="J", min_panel=1, grace_s=0.2, hard_timeout_s=3)
    assert sorted(seen) == ["a", "b"]                             # duplicate 'a' asked once


def test_fuse_task_assembles_panel(monkeypatch):
    from core import orchestrator as O
    monkeypatch.setattr(O.registry, "model_chain",
                        lambda tier, task_type=None, max_len=4: ["x/a", "y/b", "z/c"])
    cap = {}

    def fake_fuse(question, panel_models, **kw):
        cap["q"] = question
        cap["panel"] = list(panel_models)
        return "FUSED-OUT"

    monkeypatch.setattr(O.fusion, "fuse", fake_fuse)
    out = O.fuse_task("hard q", budget=O.Budget())
    assert out == "FUSED-OUT" and cap["q"] == "hard q"
    assert 2 <= len(cap["panel"]) and set(cap["panel"]) <= {"x/a", "y/b", "z/c"}


def test_fuse_task_single_model_falls_back_to_one_answer(monkeypatch):
    from core import orchestrator as O
    monkeypatch.setattr(O.registry, "model_chain",
                        lambda tier, task_type=None, max_len=4: ["only/one"])
    monkeypatch.setattr(O, "complete_chain", lambda models, messages, **kw: _resp("SINGLE"))
    out = O.fuse_task("q", budget=O.Budget())
    assert out == "SINGLE"                                        # <2 models -> answer once, no panel
