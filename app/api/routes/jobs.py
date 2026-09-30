import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import get_pipeline, get_store
from app.audio.probe import probe_duration
from app.core.config import MAX_UPLOAD_BYTES
from app.core.errors import AppError, UnknownSpeaker, UploadTooLarge
from app.jobs.store import JobStore
from app.pipeline import Pipeline
from app.schemas.job import TERMINAL_STAGES, Job
from app.schemas.minutes import Minutes
from app.schemas.transcript import NamedTurn, TranscriptView

router = APIRouter(prefix="/jobs", tags=["jobs"])
READ_SIZE = 1024 * 1024


async def save_upload(upload: UploadFile, dst: Path):
    written = 0
    with dst.open("wb") as out:
        while chunk := await upload.read(READ_SIZE):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise UploadTooLarge(f"file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
            out.write(chunk)


def transcript_view(store: JobStore, job: Job) -> TranscriptView:
    turns = store.load_turns(job.id)
    speakers = {s: job.speaker_names.get(s, s) for s in sorted({t.speaker for t in turns})}
    return TranscriptView(speakers=speakers, turns=[NamedTurn(**t.model_dump(), name=speakers[t.speaker]) for t in turns])


@router.post("", status_code=202, response_model=Job)
async def create_job(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    store: JobStore = Depends(get_store),
    pipeline: Pipeline = Depends(get_pipeline),
):
    filename = Path(file.filename or "upload").name
    job = store.create(filename)
    source = store.dir(job.id) / f"source{Path(filename).suffix.lower()}"
    try:
        await save_upload(file, source)
        await asyncio.to_thread(probe_duration, source)
    except AppError:
        store.delete(job.id)
        raise
    job = store.update(job.id, source=source.name)
    background.add_task(pipeline.run, job.id)
    return job


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, store: JobStore = Depends(get_store)):
    return store.get(job_id)


@router.get("/{job_id}/events")
def job_events(job_id: str, store: JobStore = Depends(get_store)):
    store.get(job_id)

    async def stream():
        last = None
        while True:
            job = store.get(job_id)
            if job.stage != last:
                last = job.stage
                yield f"event: stage\ndata: {job.model_dump_json()}\n\n"
            if job.stage in TERMINAL_STAGES:
                return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{job_id}/transcript", response_model=TranscriptView)
def get_transcript(job_id: str, store: JobStore = Depends(get_store)):
    return transcript_view(store, store.require_done(job_id))


@router.get("/{job_id}/minutes", response_model=Minutes)
def get_minutes(job_id: str, store: JobStore = Depends(get_store)):
    store.require_done(job_id)
    return store.load_minutes(job_id)


@router.patch("/{job_id}/speakers", response_model=TranscriptView)
def rename_speakers(job_id: str, names: dict[str, str] = Body(...), store: JobStore = Depends(get_store)):
    job = store.require_done(job_id)
    unknown = sorted(set(names) - {t.speaker for t in store.load_turns(job_id)})
    if unknown:
        raise UnknownSpeaker(f"unknown speakers: {', '.join(unknown)}")
    merged = dict(job.speaker_names)
    for speaker, name in names.items():
        if name.strip():
            merged[speaker] = name.strip()
        else:
            merged.pop(speaker, None)
    return transcript_view(store, store.update(job_id, speaker_names=merged))


@router.post("/{job_id}/minutes", response_model=Minutes)
async def regenerate_minutes(job_id: str, pipeline: Pipeline = Depends(get_pipeline)):
    return await pipeline.regenerate_minutes(job_id)
