"""memory.py — REST for semantic 'profile' facts (view / add / forget).

Lets the user see exactly what the agent has remembered about them and delete or add
facts — the inspect/forget control that keeps semantic memory from going stale or
storing something unwanted.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import memory

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
def list_facts(scope: Optional[str] = None):
    return memory.list_facts(scope)


class FactIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    key: str = Field(min_length=1, max_length=60)
    scope: str = "global"


@router.post("")
def add_fact(body: FactIn):
    memory.upsert_fact(body.text, body.key, body.scope or "global")
    return {"ok": True, "facts": memory.list_facts()}


@router.delete("/{fact_id}")
def forget(fact_id: str):
    if not memory.forget_fact(fact_id):
        raise HTTPException(404, "fact not found")
    return {"ok": True, "facts": memory.list_facts()}


# ---- procedural rules (proposed -> human-approved -> active) ----------------
@router.get("/rules")
def list_rules(status: Optional[str] = None):
    return memory.list_rules(status)


class RuleIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    scope: str = "global"


@router.post("/rules")
def add_rule(body: RuleIn):
    # Manually added rules are active immediately (the user is the author).
    memory.add_rule(body.text, body.scope or "global", proposed=False)
    return {"ok": True, "rules": memory.list_rules()}


@router.post("/rules/{rule_id}/approve")
def approve_rule(rule_id: str):
    if not memory.approve_rule(rule_id):
        raise HTTPException(404, "proposed rule not found")
    return {"ok": True, "rules": memory.list_rules()}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str):
    if not memory.delete_rule(rule_id):
        raise HTTPException(404, "rule not found")
    return {"ok": True, "rules": memory.list_rules()}
