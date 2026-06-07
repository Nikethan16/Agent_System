"""benchmark.py — REST for the Model Lab (score + compare models)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import benchmark
from core.registry import registry

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


@router.get("/cases")
def cases():
    return {
        "aspects": benchmark.aspects(),
        "modes": ["raw", "pipeline", "both"],
        "models": [m["id"] for m in registry.catalog()],
    }


class RunIn(BaseModel):
    model: str = Field(min_length=1)
    mode: str = "both"


@router.post("/run")
def run(body: RunIn):
    try:
        rid = benchmark.start_run(body.model, body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": rid}


@router.get("/runs")
def runs():
    return benchmark.list_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    r = benchmark.get_run(run_id)
    if not r:
        raise HTTPException(404, "benchmark run not found")
    return r
