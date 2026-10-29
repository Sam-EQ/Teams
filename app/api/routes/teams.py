from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import get_pipeline, get_store, get_teams
from app.core.config import DIARIZATION_ENGINE
from app.jobs.store import JobStore
from app.pipeline import Pipeline
from app.schemas.job import Job, TeamsJobRequest
from app.services.diarization import check_engine
from app.services.teams import TeamsClient

router = APIRouter(prefix="/jobs", tags=["teams"])


@router.post("/teams", status_code=202, response_model=Job)
async def create_teams_job(
    body: TeamsJobRequest,
    background: BackgroundTasks,
    store: JobStore = Depends(get_store),
    pipeline: Pipeline = Depends(get_pipeline),
    teams: TeamsClient = Depends(get_teams),
):
    engine = check_engine(body.engine or DIARIZATION_ENGINE)
    meeting_id, subject = await teams.find_meeting(body.join_url.strip())
    recording_id = await teams.latest_recording(meeting_id)
    job = store.create(f"{subject}.mp4", engine)
    background.add_task(pipeline.run_teams, job.id, meeting_id, recording_id)
    return job
