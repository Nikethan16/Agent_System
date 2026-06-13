"""fleet.py — REST for managing the model fleet from the UI:
  * /api/keys     — view (masked) + add/remove/test API keys per provider (the pool)
  * /api/routing  — view + edit the per-task fallback chains
  * /api/usage    — live per-key rate-limit usage/health

Keys are SECRETS: they're never returned in full (only a masked label), never logged,
and stored in a gitignored file (data/keys.json). The whole router is behind the auth gate.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import keypool
from core.registry import registry
from core.llm import complete, Budget

router = APIRouter(prefix="/api", tags=["fleet"])


# ---- API keys (the pool) ----------------------------------------------------
def _keys_view() -> dict:
    store = keypool._load_store()
    out = {}
    for prov in keypool._PROVIDER_ENV:
        pool = keypool.get_pool(prov)
        if not pool or not pool.keys:
            continue
        store_masked = {keypool.mask(k) for k in (store.get(prov) or [])}
        out[prov] = [{**r, "removable": r["key"] in store_masked} for r in pool.report()]
    return out


@router.get("/keys")
def list_keys():
    return _keys_view()


class KeyIn(BaseModel):
    provider: str = Field(min_length=2)
    key: str = Field(min_length=6, max_length=400)


@router.post("/keys")
def add_key(body: KeyIn):
    try:
        keypool.add_key(body.provider, body.key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _keys_view()


@router.delete("/keys/{provider}/{masked}")
def remove_key(provider: str, masked: str):
    keypool.remove_key(provider, masked)
    return _keys_view()


class ProviderIn(BaseModel):
    provider: str = Field(min_length=2)


@router.post("/keys/test")
def test_provider(body: ProviderIn):
    """Fire one tiny real call through the pool to confirm the provider's key(s) work."""
    model = next((m["id"] for m in registry.catalog()
                  if keypool.provider_of(m["id"]) == body.provider), None)
    if not model:
        raise HTTPException(400, "no catalog model for that provider")
    try:
        resp, _ = complete(model, [{"role": "user", "content": "Reply with exactly: OK"}],
                           max_tokens=8, budget=Budget(max_usd=0.2, max_iterations=2))
        return {"ok": True, "model": model, "reply": (resp.choices[0].message.content or "")[:60]}
    except Exception as e:
        return {"ok": False, "model": model, "error": f"{type(e).__name__}: {str(e)[:140]}"}


@router.get("/usage")
def usage():
    return keypool.report_all()


# ---- routing (view + edit the fallback chains) ------------------------------
@router.get("/routing")
def get_routing():
    r = registry.routing()
    resolved = {tt: registry.model_chain("tier3", tt) for tt in r}   # what's actually used
    return {"routing": r, "resolved": resolved}


class RoutingIn(BaseModel):
    task_type: str = Field(min_length=1, max_length=40)
    chain: list


@router.put("/routing")
def set_routing(body: RoutingIn):
    return {"ok": True, "routing": registry.set_routing(body.task_type, body.chain)}
