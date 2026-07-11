"""UI-editable per-use-case routing: set/reset overrides persist to data/routing.json,
override models.yaml, keep only catalog-known ids, and model_chain reflects them."""
import pytest

import core.registry as registry_mod
from core.registry import ModelRegistry


@pytest.fixture()
def reg(tmp_path):
    orig = (registry_mod.ROUTING_PATH, registry_mod.DISCOVERED_PATH)
    registry_mod.ROUTING_PATH = str(tmp_path / "routing.json")
    registry_mod.DISCOVERED_PATH = str(tmp_path / "discovered.yaml")
    try:
        yield ModelRegistry()
    finally:
        (registry_mod.ROUTING_PATH, registry_mod.DISCOVERED_PATH) = orig


def test_set_routing_overrides_and_persists(reg, tmp_path):
    known = reg.catalog()[0]["id"]
    reg.set_routing("coding", [known])
    assert reg.routing()["coding"] == [known]
    # A fresh registry reading the same override file sees it (persistence).
    reg2 = ModelRegistry()
    assert reg2.routing()["coding"] == [known]
    assert "coding" in reg2.routing_overrides()


def test_set_routing_drops_unknown_ids(reg):
    known = reg.catalog()[0]["id"]
    reg.set_routing("coding", [known, "made/up/model", "also/fake"])
    assert reg.routing()["coding"] == [known]      # unknowns stripped


def test_reset_reverts_to_yaml_default(reg):
    default_coding = reg.base_routing().get("coding")
    known = reg.catalog()[0]["id"]
    reg.set_routing("coding", [known])
    assert reg.routing()["coding"] == [known]
    reg.reset_routing("coding")
    assert reg.routing().get("coding") == default_coding
    assert "coding" not in reg.routing_overrides()


def test_model_chain_uses_override(reg, monkeypatch):
    # Pick a catalog model that has NO key requirement or force it available, then make
    # it the sole coding chain and confirm model_chain returns it first.
    monkeypatch.setattr(ModelRegistry, "_available", staticmethod(lambda m: True))
    r = ModelRegistry()
    r.set_routing("coding", ["gemini/gemini-2.5-flash-lite"])
    chain = r.model_chain("tier1", task_type="coding")
    assert chain[0] == "gemini/gemini-2.5-flash-lite"
