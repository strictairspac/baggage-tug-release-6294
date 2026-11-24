from fastapi import APIRouter, Depends, HTTPException, Response

from src.config.resources import engine
from src.constants.job_state import JobState
from src.controllers.access import identity, reviewer
from src.controllers.workbench import new_review
from src.schemas.reviews import ReviewEntry, ReviewInput
from src.schemas.runs import RunEntry, RunItemEntry
from src.services import reviews, runs
from src.utils.serial import canonical_json

router = APIRouter(prefix="/runs", tags=["Execution"])


@router.get("", response_model=list[RunEntry], dependencies=[Depends(identity)])
def list_runs():
    with engine.connect() as db:
        return runs.list_entries(db)


@router.get("/{run_id}", response_model=RunEntry, dependencies=[Depends(identity)])
def run_detail(run_id: int):
    with engine.connect() as db:
        return runs.get(db, run_id)


@router.get("/{run_id}/review", response_model=ReviewEntry | None, dependencies=[Depends(identity)])
def review_detail(run_id: int):
    with engine.connect() as db:
        runs.get(db, run_id)
        return reviews.get(db, run_id)


@router.post("/{run_id}/review", response_model=ReviewEntry, status_code=201)
def sign(run_id: int, form: ReviewInput, user=Depends(reviewer)):
    return new_review(run_id, form, user)


@router.get("/{run_id}/items", response_model=list[RunItemEntry], dependencies=[Depends(identity)])
def run_items(run_id: int):
    with engine.connect() as db:
        runs.get(db, run_id)
        return runs.items(db, run_id)


@router.get("/{run_id}/export", dependencies=[Depends(identity)])
def export(run_id: int):
    with engine.connect() as db:
        run = runs.get(db, run_id)
        if run["status"] != JobState.DONE or run["remaining"]:
            raise HTTPException(409, "整批车辆核齐后才能导出证据")
        run["review"] = reviews.get(db, run_id)
        # The frozen verification data is part of the evidence: it shows exactly
        # what the batch was screened against.
        evidence = {key: run[key] for key in (
            "id", "case_id", "case_title", "status", "parameter", "actor", "created_at",
            "started_at", "finished_at", "total", "result", "digest", "snapshot", "review",
        )}
    return Response(canonical_json(evidence), media_type="application/json", headers={
        "Content-Disposition": f"attachment; filename=evidence-{run_id}.json",
    })
