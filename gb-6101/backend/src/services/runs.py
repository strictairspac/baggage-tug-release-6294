from time import time

from fastapi import HTTPException
from sqlalchemy import insert, select

from src.constants.job_state import JobState
from src.domain import scenario
from src.domain.scenario import CONFIG
from src.models.cases import cases
from src.models.run_items import run_items
from src.models.runs import runs
from . import audit, cases as case_service


def query():
    return select(runs, cases.c.title.label("case_title")).join(cases, cases.c.id == runs.c.case_id)


def _entry(row):
    run = dict(row)
    run["checked"] = run["checked"] or 0
    return run


def get(db, run_id):
    run = db.execute(query().where(runs.c.id == run_id)).mappings().first()
    if run is None:
        raise HTTPException(404, "执行批次不存在")
    return _entry(run)


def list_entries(db):
    return [
        _entry(row) for row in db.execute(query().order_by(runs.c.id.desc()).limit(100)).mappings()
    ]


def items(db, run_id):
    """Per-vehicle progress of a batch; internal lease fields stay private."""
    return [
        {key: row[key] for key in ("position", "asset", "status", "result", "failure", "attempts")}
        for row in db.execute(
            select(run_items).where(run_items.c.run_id == run_id).order_by(run_items.c.position)
        ).mappings()
    ]


def enqueue(db, case_id, parameter, actor):
    if parameter > CONFIG["max_parameter"]:
        raise HTTPException(422, f"参数不能超过 {CONFIG['max_parameter']}")
    case = case_service.get(db, case_id)
    try:
        scenario.validate(case["payload"])
        scenario.check_parameter(parameter)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Freeze the verification data of the batch here: every vehicle in the batch
    # is screened against this snapshot and this review minute, even if the case
    # is edited or a worker restarts later.
    snapshot = case["payload"]
    total = len(snapshot["vehicles"])
    change = db.execute(insert(runs).values(
        case_id=case_id, status=JobState.QUEUED, parameter=parameter, actor=actor,
        created_at=int(time()), snapshot=snapshot, total=total, checked=0, remaining=total,
    ))
    run_id = change.inserted_primary_key[0]
    db.execute(
        insert(run_items),
        [
            {"run_id": run_id, "position": position, "asset": vehicle["asset"], "status": "queued"}
            for position, vehicle in enumerate(snapshot["vehicles"], start=1)
        ],
    )
    audit.record(db, "enqueue", actor, "run", run_id)
    return get(db, run_id)
