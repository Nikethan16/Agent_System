"""jobs.py — REST for the background task queue (enqueue / list / status)."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import jobs

router = APIRouter(prefix="/api", tags=["jobs"])


class EnqueueIn(BaseModel):
    session_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    # Hard upper bounds (the worker clamps again to the env ceiling, but reject
    # absurd values at the edge with a clear 422).
    max_usd: float = Field(default=0.5, ge=0, le=100)
    max_iterations: int = Field(default=12, ge=1, le=200)


@router.post("/enqueue")
def enqueue(body: EnqueueIn):
    return {"id": jobs.enqueue(body.session_id, body.text, body.max_usd, body.max_iterations)}


@router.get("/jobs")
def list_jobs(session_id: Optional[str] = None):
    return jobs.list_jobs(session_id)


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    j = jobs.get_job(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j
