from datetime import datetime
from typing import Literal, TypedDict

TaskStatus = Literal["queued", "running", "succeeded", "failed"]


class Task(TypedDict):
    id: int
    repository: str
    run_id: int
    run_attempt: int
    commit_sha: str
    branch: str | None
    status: TaskStatus
    attempts: int
    result: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None