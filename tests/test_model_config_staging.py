"""The finalized paid-direct model config (2026-07-11) is staged behind requires_env:

* with NO paid keys set, every chain resolves to the free NIM/Gemini fleet (old
  behavior — nothing regresses for keyless CI or the current VM);
* the moment DEEPSEEK/ZAI/DEEPINFRA keys exist, the paid directs LEAD their chains
  (plan=V4Pro, build=V4Flash, qa=GLM, research=Nemotron, data=Qwen3-Coder).
"""
import pytest

from core.registry import ModelRegistry

PAID_KEYS = ("DEEPSEEK_API_KEY", "ZAI_API_KEY", "DEEPINFRA_API_KEY")
FREE_KEYS = ("NVIDIA_NIM_API_KEY", "GEMINI_API_KEY")


@pytest.fixture()
def reg(monkeypatch, tmp_path):
    # Isolate from the developer's real env + any UI routing override.
    monkeypatch.setenv("DATA_DIR", str(tmp_path))       # empty routing.json dir
    for k in PAID_KEYS + FREE_KEYS + ("OPENROUTER_API_KEY", "USE_OLLAMA"):
        monkeypatch.delenv(k, raising=False)

    def make():
        return ModelRegistry()
    return make


def _set_free(monkeypatch):
    for k in FREE_KEYS:
        monkeypatch.setenv(k, "test-key")


def _set_paid(monkeypatch):
    for k in PAID_KEYS:
        monkeypatch.setenv(k, "test-key")


def test_no_paid_keys_falls_to_free_fleet(reg, monkeypatch):
    _set_free(monkeypatch)
    r = reg()
    for task_type in ("coding", "reasoning", "planning", "qa", "research",
                      "chat", "general", "writing", "data"):
        chain = r.model_chain("tier3", task_type=task_type)
        assert chain, f"{task_type}: empty chain"
        for mid in chain:
            assert not mid.startswith(("deepseek/", "zai/", "deepinfra/")), \
                f"{task_type}: paid model {mid} active without its key"


def test_paid_keys_activate_finalized_plan(reg, monkeypatch):
    _set_free(monkeypatch)
    _set_paid(monkeypatch)
    r = reg()
    # The finalized fit->reliability->cost assignments (2026-07-11):
    assert r.model_chain("tier3", task_type="planning")[0] == "deepseek/deepseek-v4-pro"
    assert r.model_chain("tier3", task_type="reasoning")[0] == "deepseek/deepseek-v4-pro"
    assert r.model_chain("tier3", task_type="coding")[0] == "deepseek/deepseek-v4-flash"
    assert r.model_chain("tier2", task_type="qa")[0] == "zai/glm-5.2"
    assert r.model_chain("tier2", task_type="research")[0] == "deepinfra/nvidia/nemotron-3-super-120b"
    assert r.model_chain("tier2", task_type="data")[0] == "deepinfra/qwen/qwen3-coder-480b"
    assert r.model_chain("tier1", task_type="chat")[0] == "deepseek/deepseek-v4-flash"
    # Router stays on the free reliable classifier even with paid keys.
    assert r.model_chain("tier1", task_type="classify")[0] == "gemini/gemini-2.5-flash-lite"


def test_chains_span_multiple_providers(reg, monkeypatch):
    """Overload resilience: every tool-critical chain must span >=2 providers so a
    single provider outage can't stall a run."""
    _set_free(monkeypatch)
    _set_paid(monkeypatch)
    r = reg()
    for task_type in ("coding", "reasoning", "planning", "qa", "research", "data"):
        chain = r.model_chain("tier3" if task_type != "data" else "tier2",
                              task_type=task_type)
        providers = {m.split("/")[0] for m in chain}
        assert len(providers) >= 2, f"{task_type}: single-provider chain {chain}"


def test_free_floor_survives_in_paid_chains(reg, monkeypatch):
    """Even with all paid keys set, the free NIM floor stays reachable in the
    build chain (a paid-provider outage falls back to free, not to a dead end)."""
    _set_free(monkeypatch)
    _set_paid(monkeypatch)
    r = reg()
    chain = r.model_chain("tier3", task_type="coding")
    assert any(m.startswith(("nvidia_nim/", "gemini/")) for m in chain), chain


def test_partial_keys_partial_activation(reg, monkeypatch):
    """Only DEEPSEEK_API_KEY set -> DeepSeek directs activate, z.ai/DeepInfra stay
    inert and their slots fall through to the next available model."""
    _set_free(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    r = reg()
    assert r.model_chain("tier3", task_type="coding")[0] == "deepseek/deepseek-v4-flash"
    qa = r.model_chain("tier2", task_type="qa")
    assert qa[0] == "deepseek/deepseek-v4-pro"      # GLM inert -> V4 Pro leads QA
    assert not any(m.startswith(("zai/", "deepinfra/")) for m in qa)
