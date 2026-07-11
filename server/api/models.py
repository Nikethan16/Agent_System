"""models.py — model tiers (get/swap), cost-first catalog + the model-scout."""
import json

from fastapi import APIRouter
from pydantic import BaseModel

from core.registry import registry
from core.agents import agents as agent_registry
from core import agents as team
from core.llm import Budget

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
def get_models():
    return {
        "tiers": registry.cfg["tiers"],
        "catalog": registry.catalog(),
        "strategy": registry.model_strategy(),
        "resolved": {t: registry.model_for_tier(t) for t in registry.cfg.get("tiers", {})},
    }


class TierUpdate(BaseModel):
    tier: str
    model: str


@router.post("/models/tier")
def set_tier(u: TierUpdate):
    updated = registry.set_tier_model(u.tier, u.model)
    return {"ok": True, "tier": u.tier, "config": updated}


# ---- per-use-case routing: choose which model(s) serve each task type, from the UI ----
# Persisted to data/routing.json (merged over models.yaml, survives deploys) so model
# selection is fully customizable with NO code/YAML edit. Only catalog-known ids are kept.
@router.get("/models/routing")
def get_routing():
    """Every routable use case with its EFFECTIVE chain, the yaml DEFAULT, whether it's
    been customized, and the catalog to choose from. task_types come from both the yaml
    routing keys and any override, so the editor lists them all."""
    base = registry.base_routing()
    overrides = registry.routing_overrides()
    effective = registry.routing()
    task_types = sorted(set(base) | set(overrides))
    return {
        "routing": {t: effective.get(t, []) for t in task_types},
        "defaults": base,
        "customized": sorted(overrides.keys()),
        "catalog": [{"id": m.get("id"), "free": bool(m.get("free")),
                     "tier_hint": m.get("tier_hint", 2),
                     "requires_env": m.get("requires_env"),
                     "available": registry._available(m),
                     "good_for": m.get("good_for", [])}
                    for m in registry.catalog()],
    }


class RoutingUpdate(BaseModel):
    task_type: str
    chain: list[str]


@router.post("/models/routing")
def set_routing(u: RoutingUpdate):
    routing = registry.set_routing(u.task_type, u.chain)
    return {"ok": True, "task_type": u.task_type, "routing": routing}


@router.delete("/models/routing/{task_type}")
def reset_routing(task_type: str):
    """Revert a use case to its models.yaml default."""
    routing = registry.reset_routing(task_type)
    return {"ok": True, "task_type": task_type, "routing": routing}


# ---- model-scout: research cheap/free models and propose catalog entries ----
@router.post("/models/scout")
def scout():
    budget = Budget(max_usd=0.25, max_iterations=10)
    raw = team.run(
        "model-scout",
        "Find the best LOW-COST / free / open-source models available right now for: "
        "routing (tier1), general+coding (tier2), and hard reasoning (tier3). Prefer "
        "NVIDIA NIM free, OpenRouter ':free', Gemini free tier, and Ollama. Propose "
        "catalog entries.",
        budget=budget,
    )
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        return {"proposal": data.get("models", []), "cost": round(budget.spent_usd, 4)}
    except Exception:
        return {"proposal": [], "cost": round(budget.spent_usd, 4), "raw": raw[:2000]}


class CatalogIn(BaseModel):
    models: list


@router.post("/models/catalog")
def apply_catalog(body: CatalogIn):
    """Add/replace discovered models (the scout's proposals, after you review them)."""
    return {"ok": True, "catalog": registry.update_catalog(body.models)}


@router.delete("/models/catalog/{model_id:path}")
def delete_catalog(model_id: str):
    return {"ok": True, "catalog": registry.remove_from_catalog(model_id)}


@router.get("/agents")
def get_agents():
    return [
        {"id": a.id, "label": a.label, "tier": a.tier,
         "capabilities": a.capabilities, "tools": a.tools,
         "when_to_use": a.when_to_use}
        for a in agent_registry.agents.values()
    ]
