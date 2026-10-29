from dataclasses import dataclass

import numpy as np

from app.core.errors import UnknownEngine
from app.core.config import ENGINES
from app.schemas.transcript import SpeakerSegment


@dataclass
class Diarization:
    probs: np.ndarray
    segments: list[SpeakerSegment]


def check_engine(engine: str) -> str:
    if engine not in ENGINES:
        raise UnknownEngine(f"unknown engine {engine}, use one of: {', '.join(ENGINES)}")
    return engine


def build_diarizer(engine: str):
    check_engine(engine)
    if engine == "nemotron":
        from app.services.nemotron import NemotronDiarizer

        return NemotronDiarizer()
    from app.services.who import WhoDiarizer

    return WhoDiarizer()


def build_diarizers() -> dict:
    return {engine: build_diarizer(engine) for engine in ENGINES}
