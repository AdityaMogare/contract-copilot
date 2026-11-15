"""Competition check (no LLM) + human review queue endpoints (design 08 §3)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent import reviews
from app.agent.check import run_check
from app.auth import User, require_user
from app.rag.retrieve import HopError
from app.routers.smoke import _describe

router = APIRouter()


def _agent_pool(request: Request):
    pool = request.app.state.clients.pg_agent
    if pool is None:
        raise HTTPException(503, detail={"hop": "postgres", "error": "Postgres not configured"})
    return pool


@router.post("/awards/{piid}/competition-check")
async def competition_check(piid: str, request: Request):
    if not (1 <= len(piid) <= 60) or not piid.replace("-", "").isalnum():
        raise HTTPException(422, detail="piid must be 1-60 letters, digits or dashes")
    try:
        out = await run_check(request.app.state.clients, piid)
    except HopError as e:
        raise HTTPException(503, detail={"hop": e.hop, "error": _describe(e.cause)})
    out.pop("far_chunks", None)   # full FAR text is for the agent; the API returns citations + links
    if not out["found"]:
        raise HTTPException(404, detail=f"No FY2025 Air Force award with PIID {piid}")
    return out


class Decision(BaseModel):
    decision: Literal["confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=2000)


@router.get("/reviews")
async def list_reviews(request: Request, status: Literal["open", "confirmed", "dismissed"] | None = "open"):
    return await reviews.list_items(_agent_pool(request), status)


@router.post("/reviews/{item_id}/decision")
async def decide(item_id: int, body: Decision, request: Request, user: User | None = Depends(require_user)):
    reviewer = user.oid if user else "local-dev"   # auth is off only in local dev (AUTH_REQUIRED=false)
    result, item = await reviews.decide(_agent_pool(request), item_id, body.decision, body.note, reviewer)
    if result == "not_found":
        raise HTTPException(404, detail="review item not found")
    if result == "already_decided":
        raise HTTPException(409, detail={"error": "already decided", "item": item})
    return item
