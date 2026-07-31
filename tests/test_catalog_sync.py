"""Tests for the deterministic models.dev catalog sync + the registry gap-fill layer.
All offline — a fixture stands in for models.dev, so no network is touched."""
import yaml

from server import catalog_sync as cs
from core import registry as R


# A tiny slice of the models.dev api.json shape (provider -> models -> facts).
FIXTURE = {
    "groq": {"id": "groq", "models": {
        "llama-3.3-70b-versatile": {
            "id": "llama-3.3-70b-versatile", "tool_call": True, "reasoning": False,
            "cost": {"input": 0.59, "output": 0.79},
            "limit": {"context": 131072, "output": 32768},
            "modalities": {"input": ["text"], "output": ["text"]}},
    }},
    "google": {"id": "google", "models": {
        "gemini-2.5-flash-lite": {
            "id": "gemini-2.5-flash-lite", "tool_call": True, "reasoning": True, "attachment": True,
            "cost": {"input": 0.10, "output": 0.40},
            "limit": {"context": 1048576, "output": 65536},
            "modalities": {"input": ["text", "image"], "output": ["text"]}},
    }},
    "cerebras": {"id": "cerebras", "models": {
        "llama-3.3-70b": {
            "id": "llama-3.3-70b", "tool_call": True,
            "cost": {"input": 0.85, "output": 1.20},
            "limit": {"context": 131072, "output": 8192},        # models.dev's full-ctx figure
            "modalities": {"input": ["text"], "output": ["text"]}},
    }},
    "deepseek": {"id": "deepseek", "models": {
        "deepseek-r1": {                                          # matched via :free tag-strip
            "id": "deepseek-r1", "reasoning": True, "tool_call": True,
            "cost": {"input": 0.5, "output": 2.0},
            "limit": {"context": 131072, "output": 32768}},
    }},
}


def test_tag_stripped_slug_match():
    """OpenRouter `:free` / Ollama `:8b` suffixes still resolve to the base model."""
    res = cs.sync(["openrouter/deepseek/deepseek-r1:free"], api=FIXTURE, now_iso="x")
    assert res["matched"] == ["openrouter/deepseek/deepseek-r1:free"]
    assert res["models"]["openrouter/deepseek/deepseek-r1:free"]["reasoning"] is True


def test_build_index_flattens_all_providers():
    idx = cs.build_index(FIXTURE)
    assert "llama-3.3-70b-versatile" in idx
    assert idx["gemini-2.5-flash-lite"]["vision"] is True          # image modality -> vision
    assert idx["gemini-2.5-flash-lite"]["context_window"] == 1048576


def test_sync_matches_by_slug_and_records_facts():
    ids = ["groq/llama-3.3-70b-versatile", "gemini/gemini-2.5-flash-lite",
           "deepseek/deepseek-v4-flash"]        # last one absent from the fixture
    res = cs.sync(ids, api=FIXTURE, now_iso="2026-08-01T00:00:00+00:00")
    assert set(res["matched"]) == {"groq/llama-3.3-70b-versatile", "gemini/gemini-2.5-flash-lite"}
    assert res["unmatched"] == ["deepseek/deepseek-v4-flash"]
    g = res["models"]["groq/llama-3.3-70b-versatile"]
    assert g["context_window"] == 131072 and g["tool_call"] is True
    assert g["synced_price"] == {"input": 0.59, "output": 0.79}
    assert "cost" in g                            # derived rank (gap-filler)
    lite = res["models"]["gemini/gemini-2.5-flash-lite"]
    assert lite["vision"] is True and lite["reasoning"] is True


def test_write_and_reload_roundtrip(tmp_path):
    res = cs.sync(["groq/llama-3.3-70b-versatile"], api=FIXTURE, now_iso="2026-08-01T00:00:00+00:00")
    p = tmp_path / "models.synced.yaml"
    cs.write_synced(res, path=str(p))
    loaded = yaml.safe_load(p.read_text())
    assert loaded["models"]["groq/llama-3.3-70b-versatile"]["context_window"] == 131072
    assert loaded["source"] == cs.MODELS_DEV_URL


def test_registry_gap_fill_base_always_wins(tmp_path, monkeypatch):
    """The whole safety property: synced facts fill a MISSING field, but NEVER clobber a
    value the owner set in models.yaml."""
    synced = {"synced_at": "x", "source": "models.dev", "models": {
        # gemini-flash-lite has NO context_window in models.yaml -> synced should fill it
        "gemini/gemini-2.5-flash-lite": {"context_window": 1048576, "tool_call": True, "vision": True},
        # cerebras has context_window: 8192 pinned in models.yaml -> synced 131072 must be IGNORED
        "cerebras/llama-3.3-70b": {"context_window": 131072},
    }}
    p = tmp_path / "models.synced.yaml"
    p.write_text(yaml.safe_dump(synced))
    monkeypatch.setattr(R, "SYNCED_PATH", str(p))
    reg = R.ModelRegistry()                       # fresh instance reads the patched path
    cat = {m["id"]: m for m in reg.catalog()}

    # gap filled:
    assert cat["gemini/gemini-2.5-flash-lite"].get("context_window") == 1048576
    assert cat["gemini/gemini-2.5-flash-lite"].get("tool_call") is True   # new capability metadata
    # base value protected (NOT clobbered):
    assert cat["cerebras/llama-3.3-70b"]["context_window"] == 8192


def test_registry_offline_without_synced_file(monkeypatch, tmp_path):
    """No synced file present -> registry loads fine, catalog unchanged (offline-safe)."""
    monkeypatch.setattr(R, "SYNCED_PATH", str(tmp_path / "does-not-exist.yaml"))
    reg = R.ModelRegistry()
    assert reg._synced == {}
    assert len(reg.catalog()) > 0
