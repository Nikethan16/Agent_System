"""Tests for the circuit-breaker tuning (core/llm.py):
trip only after N consecutive failures, never on EmptyResponse, reset on success,
and the last model in a chain is always attempted even when others are open."""
import time

import pytest

from core import llm
from core.llm import complete_chain, EmptyResponse


@pytest.fixture(autouse=True)
def _clear_breaker():
    llm._BREAKER.clear(); llm._BREAKER_FAILS.clear()
    yield
    llm._BREAKER.clear(); llm._BREAKER_FAILS.clear()


class _OK:
    choices = [object()]   # truthy — a "successful" response


def _ok(*a, **k):
    return (_OK(), 0.0)


def test_one_failure_does_not_open(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("slow")))
    with pytest.raises(TimeoutError):
        complete_chain(["m1"], [{"role": "user", "content": "x"}])
    assert not llm._breaker_open("m1")          # 1 failure < threshold (2) -> stays closed
    assert llm._BREAKER_FAILS.get("m1") == 1


def test_threshold_consecutive_failures_open(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("slow")))
    with pytest.raises(TimeoutError):
        complete_chain(["m1"], [{"role": "user", "content": "x"}])
    assert not llm._breaker_open("m1")
    with pytest.raises(TimeoutError):
        complete_chain(["m1"], [{"role": "user", "content": "x"}])
    assert llm._breaker_open("m1")              # 2nd consecutive failure opens it


def test_success_resets_counter(monkeypatch):
    state = {"fail": True}

    def fake(model, *a, **k):
        if state["fail"]:
            raise TimeoutError("x")
        return _ok()

    monkeypatch.setattr(llm, "complete", fake)
    with pytest.raises(TimeoutError):
        complete_chain(["m1"], [{"role": "user", "content": "x"}])
    assert llm._BREAKER_FAILS.get("m1") == 1
    state["fail"] = False
    complete_chain(["m1"], [{"role": "user", "content": "x"}])
    assert "m1" not in llm._BREAKER_FAILS        # success cleared the counter


def test_empty_response_never_trips(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(EmptyResponse("empty")))
    for _ in range(5):
        with pytest.raises(EmptyResponse):
            complete_chain(["m1"], [{"role": "user", "content": "x"}])
    assert not llm._breaker_open("m1")           # benign empties don't bench the model
    assert "m1" not in llm._BREAKER_FAILS


def test_last_model_attempted_when_others_open(monkeypatch):
    llm._BREAKER["m1"] = time.time() + 60        # force m1, m2 open
    llm._BREAKER["m2"] = time.time() + 60
    seen = []

    def fake(model, *a, **k):
        seen.append(model)
        return _ok()

    monkeypatch.setattr(llm, "complete", fake)
    complete_chain(["m1", "m2", "m3"], [{"role": "user", "content": "x"}])
    assert seen == ["m3"]                         # open ones skipped; last is always tried
