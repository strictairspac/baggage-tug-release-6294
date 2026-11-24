from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, String, Table, UniqueConstraint

from .base import metadata


# One row per vehicle in a screening batch. Rows are claimed independently so a
# later small batch can finish while a large batch is still being checked, and
# finished rows survive worker restarts.
run_items = Table(
    "run_items", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("position", Integer, nullable=False),
    Column("asset", String(64), nullable=False),
    Column("status", String(16), nullable=False, index=True),
    Column("result", JSON(none_as_null=True), nullable=True),
    Column("failure", String(320), nullable=True),
    Column("attempts", Integer, nullable=False, server_default="0"),
    # Fencing token: incremented on every claim. A result written with an old
    # token after another worker took the item over is discarded.
    Column("claim_token", BigInteger, nullable=False, server_default="0"),
    Column("claimed_by", String(64), nullable=True),
    Column("lease_until", BigInteger, nullable=True),
    Column("last_claimed_at", BigInteger, nullable=True),
    Column("finished_at", BigInteger, nullable=True),
    UniqueConstraint("run_id", "asset", name="uq_run_items_asset"),
    UniqueConstraint("run_id", "position", name="uq_run_items_position"),
)
