from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ItemState(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


ACTIVE_JOB_STATES = (JobState.QUEUED, JobState.RUNNING)
