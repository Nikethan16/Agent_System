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
