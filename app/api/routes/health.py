import asyncio

from fastapi import APIRouter, Request

from app.core.config import DIARIZATION_ENGINE, KEYWORDS, MINUTES_MODEL, TIMING_MODEL, TRANSCRIBE_MODEL

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    services = request.app.state.services
    engines = {name: await asyncio.to_thread(d.health) for name, d in services.diarizers.items()}
    return {
        "ok": True,
        "default_engine": DIARIZATION_ENGINE,
        "engines": engines,
        "transcribe_model": TRANSCRIBE_MODEL,
        "timing_model": TIMING_MODEL,
        "minutes_model": MINUTES_MODEL,
        "keywords": KEYWORDS,
        "teams_import": services.teams is not None,
    }
