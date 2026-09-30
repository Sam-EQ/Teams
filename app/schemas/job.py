from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Stage(str, Enum):
    queued = "queued"
    downloading = "downloading"
    extracting = "extracting"
    analyzing = "analyzing"
    stitching = "stitching"
    minutes = "minutes"
    done = "done"
    failed = "failed"


TERMINAL_STAGES = {Stage.done, Stage.failed}


class JobStats(BaseModel):
    duration_seconds: float
    speakers: int
    turns: int
    gaps_filled: int
    processing_seconds: float


class Job(BaseModel):
    id: str
    filename: str
    source: str | None = None
    stage: Stage = Stage.queued
    error: str | None = None
    error_stage: Stage | None = None
    speaker_names: dict[str, str] = {}
    stats: JobStats | None = None
    created_at: datetime
    updated_at: datetime


class TeamsJobRequest(BaseModel):
    join_url: str
