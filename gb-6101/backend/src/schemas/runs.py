from pydantic import BaseModel, Field
from src.constants.job_state import ItemState, JobState


class RunInput(BaseModel):
    parameter: int = Field(strict=True, ge=1)


class RunEntry(BaseModel):
    id: int
    case_id: int
    case_title: str
    status: JobState
    parameter: int
    actor: str
    created_at: int
    started_at: int | None = None
    finished_at: int | None
    total: int | None = None
    checked: int = 0
    remaining: int | None = None
    result: dict | None
    failure: str | None
    digest: str | None


class RunItemEntry(BaseModel):
    position: int
    asset: str
    status: ItemState
    result: dict | None = None
    failure: str | None = None
    attempts: int = 0

