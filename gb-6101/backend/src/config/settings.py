import os

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET = os.environ["JWT_SECRET"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]
SEED_DEMO = os.environ.get("SEED_DEMO", "true").lower() == "true"
# How long a worker owns one claimed vehicle before another worker may take it over.
WORKER_LEASE_SECONDS = max(1, int(os.environ.get("WORKER_LEASE_SECONDS", "10")))
# Claims allowed for one vehicle before its batch is failed.
WORKER_MAX_ATTEMPTS = max(1, int(os.environ.get("WORKER_MAX_ATTEMPTS", "3")))
# Name of this execution machine, kept in each claim for troubleshooting.
WORKER_ID = os.environ.get("WORKER_ID", "")
