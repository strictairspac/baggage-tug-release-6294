import logging
import time

from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.config.resources import cache, engine
from src.services.execution import reap, service_one

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

HEARTBEAT = 90


def check():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    heartbeat = cache.get("workbench:heartbeat")
    return heartbeat is not None and time.time() - float(heartbeat) < HEARTBEAT


def work():
    while True:
        try:
            cache.set("workbench:heartbeat", time.time(), ex=HEARTBEAT)
            drained = True
            while service_one():
                cache.set("workbench:heartbeat", time.time(), ex=HEARTBEAT)
            drained = not reap()
            if drained:
                cache.blpop("workbench:wake", timeout=1)
        except (RedisError, SQLAlchemyError):
            logger.exception("Worker connection unavailable")
            time.sleep(2)
        except Exception:
            # An unexpected error must not stop this worker for good.
            logger.exception("Worker iteration failed, retrying")
            time.sleep(1)
