import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter
from pydantic_core import to_json

from app.core.errors import JobNotFound, JobNotReady
from app.schemas.job import TERMINAL_STAGES, Job, Stage
from app.schemas.minutes import Minutes
from app.schemas.transcript import Turn

JOB_ID = re.compile(r"^[0-9a-f]{12}$")
TURNS = TypeAdapter(list[Turn])


def now() -> datetime:
    return datetime.now(timezone.utc)


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def dir(self, job_id: str) -> Path:
        if not JOB_ID.match(job_id):
            raise JobNotFound(f"job {job_id} not found")
        return self.root / job_id

    def create(self, filename: str, engine: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], filename=filename, engine=engine, created_at=now(), updated_at=now())
        self.dir(job.id).mkdir(parents=True)
        self.save(job)
        return job

    def get(self, job_id: str) -> Job:
        path = self.dir(job_id) / "job.json"
        if not path.exists():
            raise JobNotFound(f"job {job_id} not found")
        return Job.model_validate_json(path.read_text())

    def save(self, job: Job):
        job.updated_at = now()
        path = self.dir(job.id) / "job.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(job.model_dump_json(indent=2))
        tmp.replace(path)

    def update(self, job_id: str, **fields) -> Job:
        job = self.get(job_id).model_copy(update=fields)
        self.save(job)
        return job

    def delete(self, job_id: str):
        shutil.rmtree(self.dir(job_id), ignore_errors=True)

    def require_done(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.stage != Stage.done:
            raise JobNotReady(f"job {job_id} is {job.stage.value}")
        return job

    def write(self, job_id: str, name: str, data):
        (self.dir(job_id) / f"{name}.json").write_bytes(to_json(data, indent=2))

    def load_turns(self, job_id: str) -> list[Turn]:
        return TURNS.validate_json((self.dir(job_id) / "transcript.json").read_bytes())

    def load_minutes(self, job_id: str) -> Minutes:
        return Minutes.model_validate_json((self.dir(job_id) / "minutes.json").read_bytes())

    def fail_interrupted(self):
        for path in self.root.glob("*/job.json"):
            job = Job.model_validate_json(path.read_text())
            if job.stage not in TERMINAL_STAGES:
                self.save(job.model_copy(update={"stage": Stage.failed, "error": "interrupted by server restart", "error_stage": job.stage}))
