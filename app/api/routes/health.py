from fastapi import APIRouter, Request

from app.core.config import DIARIZATION_MODE, MINUTES_MODEL, TRANSCRIBE_MODEL

router = APIRouter()


@router.get("/health")
def health(request: Request):
    return {
        "ok": True,
        "diarizer_device": request.app.state.services.diarizer.device,
        "diarization_mode": DIARIZATION_MODE,
        "transcribe_model": TRANSCRIBE_MODEL,
        "minutes_model": MINUTES_MODEL,
        "teams_import": request.app.state.services.teams is not None,
    }
