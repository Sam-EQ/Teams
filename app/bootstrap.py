from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import DATA_DIR, OPENAI_API_KEY, OPENAI_MAX_RETRIES, OPENAI_TIMEOUT_SECONDS, TEAMS_ENABLED
from app.jobs.store import JobStore
from app.pipeline import Pipeline
from app.services.diarization import Diarizer
from app.services.minutes import MinutesWriter
from app.services.teams import TeamsClient
from app.services.transcription import Transcriber


@dataclass
class Services:
    client: AsyncOpenAI
    store: JobStore
    diarizer: Diarizer
    pipeline: Pipeline
    teams: TeamsClient | None


def build_services() -> Services:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS, max_retries=OPENAI_MAX_RETRIES)
    store = JobStore(DATA_DIR)
    diarizer = Diarizer()
    teams = TeamsClient() if TEAMS_ENABLED else None
    pipeline = Pipeline(store, Transcriber(client), diarizer, MinutesWriter(client), teams)
    return Services(client=client, store=store, diarizer=diarizer, pipeline=pipeline, teams=teams)
