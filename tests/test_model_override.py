"""The composer's Model picker pins a model for a run: model_chain prepends it (routing
stays as fallback), classify keeps its cheap auto-model, and — critically — parallel
worker threads inherit the pin (contextvars don't cross ThreadPoolExecutor boundaries,
so the orchestrator must re-bind it). No keys/cost — model_chain is pure resolution."""
from core.registry import registry
from core.llm import Budget


def _clear():
    registry.set_model_override(None)


def test_override_prepends_and_keeps_routing_fallback():
    _clear()
    base = registry.model_chain("tier2", task_type="coding")
    registry.set_model_override("vendor/pinned-model")
    try:
        ch = registry.model_chain("tier2", task_type="coding")
        assert ch[0] == "vendor/pinned-model"           # pin goes to the front
        assert base[0] in ch                             # routing kept as fallback
    finally:
        _clear()


def test_override_excluded_for_classify():
    _clear()
    registry.set_model_override("vendor/pinned-model")
    try:
        cl = registry.model_chain("tier1", task_type="classify")
        assert cl[0] != "vendor/pinned-model"            # routing stays cheap for classify
    finally:
        _clear()


def test_override_clears():
    _clear()
    base = registry.model_chain("tier2", task_type="coding")
    registry.set_model_override("vendor/pinned-model")
    registry.set_model_override(None)                    # cleared
    assert registry.model_chain("tier2", task_type="coding") == base


def test_use_model_override_contextmanager_resets():
    _clear()
    with registry.use_model_override("vendor/x"):
        assert registry.get_model_override() == "vendor/x"
    assert registry.get_model_override() is None         # restored on exit


def test_model_for_tier_reflects_override_in_cheapest_mode():
    _clear()
    registry.set_model_override("vendor/pinned-model")
    try:
        # cheapest strategy resolves via model_chain -> the assign-event model shows the pin
        assert registry.model_for_tier("tier2", task_type="coding") == "vendor/pinned-model"
        # ...but not for classify
        assert registry.model_for_tier("tier1", task_type="classify") != "vendor/pinned-model"
    finally:
        _clear()


def test_parallel_workers_inherit_the_pin(monkeypatch):
    """The regression: ThreadPoolExecutor workers don't inherit contextvars, so without
    the orchestrator's re-bind each parallel agent would silently run on the AUTO model
    instead of the pinned one."""
    from core import orchestrator as orch
    seen = []

    def fake_run(agent_id, instruction, **kw):
        seen.append(registry.get_model_override())       # what the worker THREAD sees
        return "ok"

    monkeypatch.setattr(orch.team, "run", fake_run)
    _clear()
    registry.set_model_override("vendor/pinned-model")
    try:
        specs = [{"agent": "research", "instruction": "a"},
                 {"agent": "research", "instruction": "b"},
                 {"agent": "research", "instruction": "c"}]
        orch._run_agents_parallel(specs, Budget(), None, None)
    finally:
        _clear()
    assert seen == ["vendor/pinned-model"] * 3, seen     # every worker saw the pin
