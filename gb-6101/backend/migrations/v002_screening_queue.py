from sqlalchemy import inspect, text

from src.models import run_items  # Register the table.
from src.models.run_items import run_items as run_items_table
from src.models.base import metadata


RUN_COLUMNS = (
    ("started_at", "BIGINT"),
    ("snapshot", "JSON"),
    ("total", "INTEGER"),
    ("checked", "INTEGER NOT NULL DEFAULT 0"),
    ("remaining", "INTEGER"),
)


def upgrade(connection):
    """Add the per-vehicle queue pieces to a database created by version 1."""
    existing = {column["name"] for column in inspect(connection).get_columns("runs")}
    for name, ddl in RUN_COLUMNS:
        if name not in existing:
            connection.execute(text(f"ALTER TABLE runs ADD COLUMN {name} {ddl}"))
    run_items_table.create(connection, checkfirst=True)
    # Batches accepted before this version have no frozen data or queue rows, so
    # they cannot be resumed. Close them honestly instead of leaving them queued.
    connection.execute(text(
        "UPDATE runs SET status = 'failed', remaining = 0, finished_at = EXTRACT(EPOCH FROM NOW())::BIGINT, "
        "failure = COALESCE(failure, '升级前的批次未入逐车队列，请重新提交') "
        "WHERE status IN ('queued', 'running')"
    ))
