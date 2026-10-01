"""
Endpoints defined in Design Doc Section 5 but not yet built — Tuesday-
Wednesday work per the Week 4 Build Plan (entity resolution, review
queue, agents). Returning 501 with a clear message here rather than a
fake empty list, so "no results" is never confused with "not built yet."
"""
from fastapi import APIRouter, Depends, HTTPException
from app.api.v1.deps import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])

PENDING_MSG = "Not yet implemented — scheduled for Week 4 Tuesday/Wednesday per the build plan."


@router.get("/persons")
def list_persons():
    raise HTTPException(501, PENDING_MSG + " (requires entity resolution)")


@router.get("/persons/{person_id}")
def get_person(person_id: str):
    raise HTTPException(501, PENDING_MSG + " (requires entity resolution)")


@router.get("/review/queue")
def review_queue():
    raise HTTPException(501, PENDING_MSG + " (requires the Entity-Resolution Adjudicator)")


@router.post("/review/{item_id}/decide")
def review_decide(item_id: str):
    raise HTTPException(501, PENDING_MSG + " (requires the review queue)")


@router.get("/traces/{run_id}")
def get_traces(run_id: str):
    raise HTTPException(501, PENDING_MSG + " (agents don't exist yet to produce traces)")


@router.get("/export")
def export():
    raise HTTPException(501, PENDING_MSG + " (requires the exposure table, which requires entity resolution)")
