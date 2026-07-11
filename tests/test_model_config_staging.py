"""The finalized paid-direct model config (2026-07-11) is staged behind requires_env:

* with NO paid keys set, every chain resolves to the free NIM/Gemini fleet, and the
  free FALLBACK ORDER is byte-identical to main (no benchmarked backup lost);
* the moment DEEPSEEK/DEEPINFRA keys exist, the paid directs LEAD their chains
  (plan=V4Pro, build=V4Flash, qa/review=GLM@DeepInfra, research=Nemotron, data=Qwen3-Coder);
* the router-emittable task_types math/frontend/review all have real chains.

Isolation note: ROUTING_PATH / DISCOVERED_PATH are computed at import time from DATA_DIR,
so setenv after import is a no-op — we monkeypatch the module globals directly (a stray
data/routing.json from the Settings UI would otherwise silently override models.yaml).
"""
import pytest

import core.registry as registry_mod
from core.registry import ModelRegistry

PAID_KEYS = ("DEEPSEEK_API_KEY", "DEEPINFRA_API_KEY", "ZAI_API_KEY")
FREE_KEYS = ("NVIDIA_NIM_API_KEY", "GEMINI_API_KEY")


@pytest.fixture()
def reg(monkeypatch, tmp_path):
    # Isolate from any real routing override / discovered-model file (both read the
    # module globals at ModelRegistry() construction — setattr, not setenv).
    monkeypatch.setattr(registry_mod, "ROUTING_PATH", str(tmp_path / "routing.json"))
    monkeypatch.setattr(registry_mod, "DISCOVERED_PATH", str(tmp_path / "discovered.yaml"))
    for k in PAID_KEYS + FREE_KEYS + ("OPENROUTER_API_KEY", "USE_OLLAMA"):
        monkeypatch.delenv(k, raising=False)
    return ModelRegistry


def _set_free(monkeypatch):
    for k in FREE_KEYS:
        monkeypatch.setenv(k, "test-key")


def _set_paid(monkeypatch):
    # The 2-key production set (DeepSeek + DeepInfra). ZAI intentionally left unset.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test-key")


def test_no_paid_keys_falls_to_free_fleet(reg, monkeypatch):
    _set_free(monkeypatch)
    r = reg()
    for task_type in ("coding", "reasoning", "planning", "qa", "review", "research",
                      "chat", "general", "writing", "data", "math", "frontend"):
        chain = r.model_chain("tier3", task_type=task_type)
        assert chain, f"{task_type}: empty chain"
        for mid in chain:
            assert not mid.startswith(("deepseek/", "zai/", "deepinfra/")), \
                f"{task_type}: paid model {mid} active without its key"


def test_free_fallback_order_unchanged_vs_main(reg, monkeypatch):
    """Regression guard for the review finding: replacing free entries with inert paid
    ones must not reorder the free fleet. These are main's exact free chains."""
    _set_free(monkeypatch)
    r = reg()
    # The three benchmarked free backups the review found were being dropped must lead
    # the free coding chain, in order (the 4th slot is cost-ranked auto-append — don't pin).
    assert r.model_chain("tier3", task_type="coding")[:3] == [
        "nvidia_nim/z-ai/glm-5.1",
        "nvidia_nim/qwen/qwen3.5-122b-a10b",
        "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
    ]
    # reasoning: nemotron-super leads, NIM deepseek-v4-pro is the curated first fallback
    # (NOT minimax — the review caught minimax being promoted by cost-rank auto-append).
    reasoning = r.model_chain("tier3", task_type="reasoning")
    assert reasoning[0] == "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
    assert reasoning[1] == "nvidia_nim/deepseek-ai/deepseek-v4-pro"
    assert reasoning.index("nvidia_nim/deepseek-ai/deepseek-v4-pro") < \
        reasoning.index("nvidia_nim/minimaxai/minimax-m3")


def test_paid_keys_activate_finalized_plan(reg, monkeypatch):
    _set_free(monkeypatch)
    _set_paid(monkeypatch)
    r = reg()
    assert r.model_chain("tier3", task_type="planning")[0] == "deepseek/deepseek-v4-pro"
    assert r.model_chain("tier3", task_type="reasoning")[0] == "deepseek/deepseek-v4-pro"
    assert r.model_chain("tier3", task_type="math")[0] == "deepseek/deepseek-v4-pro"
    assert r.model_chain("tier3", task_type="coding")[0] == "deepseek/deepseek-v4-flash"
    assert r.model_chain("tier3", task_type="frontend")[0] == "deepseek/deepseek-v4-flash"
    assert r.model_chain("tier2", task_type="qa")[0] == "deepinfra/zai-org/GLM-4.6"
    assert r.model_chain("tier2", task_type="review")[0] == "deepinfra/zai-org/GLM-4.6"
    assert r.model_chain("tier2", task_type="research")[0] == "deepinfra/nvidia/nemotron-3-super-120b"
    assert r.model_chain("tier2", task_type="data")[0] == "deepinfra/qwen/qwen3-coder-480b"
    assert r.model_chain("tier1", task_type="chat")[0] == "deepseek/deepseek-v4-flash"
    # Router stays on the free reliable classifier even with paid keys.
    assert r.model_chain("tier1", task_type="classify")[0] == "gemini/gemini-2.5-flash-lite"


def test_chains_span_multiple_providers(reg, monkeypatch):
    """Overload resilience: every tool-critical chain must span >=2 providers."""
    _set_free(monkeypatch)
    _set_paid(monkeypatch)
    r = reg()
    for task_type in ("coding", "reasoning", "planning", "qa", "research", "data"):
        chain = r.model_chain("tier3" if task_type != "data" else "tier2",
                              task_type=task_type)
        providers = {m.split("/")[0] for m in chain}
        assert len(providers) >= 2, f"{task_type}: single-provider chain {chain}"


def test_free_floor_survives_in_paid_chains(reg, monkeypatch):
    _set_free(monkeypatch)
    _set_paid(monkeypatch)
    r = reg()
    chain = r.model_chain("tier3", task_type="coding")
    assert any(m.startswith(("nvidia_nim/", "gemini/")) for m in chain), chain


def test_partial_keys_partial_activation(reg, monkeypatch):
    """Only DEEPSEEK_API_KEY set -> DeepSeek directs activate, DeepInfra stays inert
    and its slots fall through to the next available model."""
    _set_free(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    r = reg()
    assert r.model_chain("tier3", task_type="coding")[0] == "deepseek/deepseek-v4-flash"
    qa = r.model_chain("tier2", task_type="qa")
    assert qa[0] == "deepseek/deepseek-v4-pro"      # GLM@DeepInfra inert -> V4 Pro leads QA
    assert not any(m.startswith(("zai/", "deepinfra/")) for m in qa)


def test_all_routing_ids_exist_in_catalog(reg, monkeypatch):
    """Every model id referenced in a routing chain must have a catalog entry, or
    model_chain silently drops it (the whole chain could evaporate)."""
    r = reg()
    catalog_ids = {m["id"] for m in r.catalog()}
    for task_type, chain in (r.cfg.get("routing") or {}).items():
        for mid in chain:
            assert mid in catalog_ids, f"routing[{task_type}] references uncatalogued {mid}"
