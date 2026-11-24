import logging
import os
import socket
from time import time

from sqlalchemy import select, text, update

from src.config.resources import engine
from src.config.settings import WORKER_ID, WORKER_LEASE_SECONDS, WORKER_MAX_ATTEMPTS
from src.constants.job_state import ItemState, JobState
from src.domain import scenario
from src.models.cases import cases
from src.models.run_items import run_items
from src.models.runs import runs
from src.services.audit import record
from src.utils.serial import content_digest

logger = logging.getLogger(__name__)

ACTIVE = (ItemState.QUEUED.value, ItemState.PROCESSING.value)


def worker_name():
    """Per-process identity; WORKER_ID lets replicas sharing a hostname be told apart."""
    base = WORKER_ID or socket.gethostname()
    return f"{base}:{os.getpid()}"


def claim(worker):
    """Take one vehicle from the shared queue and commit the claim on its own.

    Batches take turns: the batch served least recently goes first, and inside a
    batch vehicles are checked in their queued order. A small batch accepted
    while a large one is still being screened therefore finishes first, without
    being starved by later arrivals. Leases let another worker take over a
    vehicle whose worker stalled, which is how an interrupted batch resumes
    without repeating the vehicles that were already checked.
    """
    now = int(time())
    served = int(time() * 1_000_000)
    with engine.begin() as db:
        item = db.execute(text("""
            WITH candidate AS (
                SELECT i.id
                FROM run_items i
                JOIN runs r ON r.id = i.run_id
                WHERE i.status IN ('queued', 'processing')
                  AND r.status IN ('queued', 'running')
                  AND (i.lease_until IS NULL OR i.lease_until <= :now)
                  AND i.attempts < :max_attempts
                ORDER BY COALESCE((
                    SELECT MAX(s.last_claimed_at) FROM run_items s WHERE s.run_id = i.run_id
                ), 0), i.position, i.id
                FOR UPDATE OF i SKIP LOCKED
                LIMIT 1
            )
            UPDATE run_items SET
                status = 'processing',
                claimed_by = :worker,
                lease_until = :now + :lease,
                last_claimed_at = :served,
                claim_token = claim_token + 1,
                attempts = attempts + 1
            WHERE id = (SELECT id FROM candidate)
            RETURNING id, run_id, asset, position, claim_token, attempts
        """), {
            "now": now, "served": served, "worker": worker, "lease": WORKER_LEASE_SECONDS,
            "max_attempts": WORKER_MAX_ATTEMPTS,
        }).mappings().first()
        if item is None:
            return None
        db.execute(
            update(runs)
            .where(runs.c.id == item["run_id"], runs.c.status == JobState.QUEUED)
            .values(status=JobState.RUNNING, started_at=now)
        )
    return item


def _reason(cause):
    if isinstance(cause, (ValueError, TypeError, KeyError, OverflowError)):
        return str(cause) or "输入资料或批次参数不符合要求"
    return "处理失败，请检查 worker 日志"


def _finish_item(item, status, result=None, failure=None):
    """Write one vehicle outcome only while this claim still owns the row.

    The claim token is incremented on every takeover, so a late result from a
    worker whose lease expired matches no row and is discarded. The status
    condition means a retry of the same claim cannot record the result twice.
    """
    with engine.begin() as db:
        changed = db.execute(
            update(run_items)
            .where(
                run_items.c.id == item["id"],
                run_items.c.claim_token == item["claim_token"],
                run_items.c.status == ItemState.PROCESSING,
            )
            .values(
                status=status, result=result, failure=failure, finished_at=int(time()),
                lease_until=None, claimed_by=None,
            )
        ).rowcount
    return changed == 1


def _settle(run_id):
    """Recompute the checked count after a vehicle finished, closing the batch when none remain."""
    now = int(time())
    with engine.begin() as db:
        run = db.execute(select(runs).where(runs.c.id == run_id).with_for_update()).mappings().first()
        if run is None:
            return
        rows = db.execute(
            select(run_items).where(run_items.c.run_id == run_id).order_by(run_items.c.position)
        ).mappings().all()
        pending = sum(row["status"] in ACTIVE for row in rows)
        checked = sum(row["status"] == ItemState.DONE for row in rows)
        db.execute(update(runs).where(runs.c.id == run_id).values(remaining=pending, checked=checked))
        if pending or run["status"] not in (JobState.QUEUED, JobState.RUNNING):
            return
        failed = next((row for row in rows if row["status"] == ItemState.FAILED), None)
        if failed is not None:
            output = {"status": JobState.FAILED, "failure": (failed["failure"] or "处理失败")[:320]}
        else:
            result = scenario.aggregate(run["parameter"], [dict(row["result"]) for row in rows])
            output = {"status": JobState.DONE, "result": result, "digest": content_digest(result)}
        db.execute(update(runs).where(runs.c.id == run_id).values(**output, remaining=0, finished_at=now))
        record(db, str(output["status"]), "worker", "run", run_id)


def _screen(item):
    """Screen one vehicle against the batch's frozen data and review minute."""
    with engine.begin() as db:
        run = db.execute(select(runs).where(runs.c.id == item["run_id"])).mappings().first()
        payload = run["snapshot"]
        if payload is None:  # Batch accepted before snapshots were introduced.
            payload = db.scalar(select(cases.c.payload).where(cases.c.id == run["case_id"]))
        scenario.validate(payload)
        return scenario.decision_rows(payload, run["parameter"], db, {item["asset"]})[0]


def service_one(worker=None):
    """Screen one vehicle; return False when no vehicle is waiting."""
    item = claim(worker or worker_name())
    if item is None:
        return False
    try:
        result = _screen(item)
    except Exception as exc:
        logger.warning("Vehicle %s of run %s failed: %s", item["asset"], item["run_id"], exc)
        if _finish_item(item, ItemState.FAILED, failure=_reason(exc)[:320]):
            _settle(item["run_id"])
        return True
    if _finish_item(item, ItemState.DONE, result=result):
        _settle(item["run_id"])
    else:
        logger.info("Discarded late result for run %s vehicle %s", item["run_id"], item["asset"])
    return True


def _open_runs():
    """Batches still open although none of their vehicles is waiting."""
    with engine.connect() as db:
        return db.execute(text("""
            SELECT r.id FROM runs r
            WHERE r.status IN ('queued', 'running')
              AND NOT EXISTS (
                  SELECT 1 FROM run_items i
                  WHERE i.run_id = r.id AND i.status IN ('queued', 'processing')
              )
        """)).scalars().all()


def reap():
    """Recover interrupted work: fail exhausted vehicles and close finished batches.

    Closing a batch is separated from writing its last vehicle, so a worker
    dying between the two steps is repaired here instead of leaving the batch
    open forever.
    """
    now = int(time())
    with engine.begin() as db:
        rows = db.execute(text("""
            UPDATE run_items SET
                status = 'failed',
                failure = '执行超时，未能在租约内完成',
                lease_until = NULL,
                claimed_by = NULL,
                finished_at = :now
            WHERE status = 'processing' AND lease_until <= :now AND attempts >= :max_attempts
            RETURNING run_id
        """), {"now": now, "max_attempts": WORKER_MAX_ATTEMPTS}).mappings().all()
    for run_id in dict.fromkeys([row["run_id"] for row in rows] + list(_open_runs())):
        _settle(run_id)
    return bool(rows)
