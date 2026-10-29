from pathlib import Path

import httpx

from app.core.config import WHO_TIMEOUT_SECONDS, WHO_URL
from app.processing.grid import to_grid
from app.schemas.transcript import SpeakerSegment
from app.services.diarization import Diarization


class WhoDiarizer:
    device = "cpu"

    def health(self) -> dict:
        try:
            return httpx.get(f"{WHO_URL}/health", timeout=5).json()
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"who engine not reachable at {WHO_URL}: {exc}"}

    def run(self, wav: Path) -> Diarization:
        try:
            response = httpx.post(f"{WHO_URL}/diarize", content=wav.read_bytes(), timeout=WHO_TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"who engine not reachable at {WHO_URL}, start engines/who first: {exc}")
        if response.is_error:
            raise RuntimeError(f"who engine failed with {response.status_code}: {response.text[:300]}")
        body = response.json()
        segments = sorted(
            (SpeakerSegment(start=t["start"], end=t["end"], speaker=f"speaker_{t['speaker']}") for t in body["turns"]),
            key=lambda s: s.start,
        )
        return Diarization(probs=to_grid(segments, body["duration"]), segments=segments)
