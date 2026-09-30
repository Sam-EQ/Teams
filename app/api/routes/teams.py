from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import get_pipeline, get_store, get_teams
from app.jobs.store import JobStore
from app.pipeline import Pipeline
from app.schemas.job import Job, TeamsJobRequest
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
    meeting_id, subject = await teams.find_meeting(body.join_url.strip())
    recording_id = await teams.latest_recording(meeting_id)
    job = store.create(f"{subject}.mp4")
    background.add_task(pipeline.run_teams, job.id, meeting_id, recording_id)
    return job
