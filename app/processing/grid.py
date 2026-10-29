import math

import numpy as np

from app.core.config import FRAME_SECONDS
from app.schemas.transcript import SpeakerSegment


def speaker_index(label: str) -> int:
    return int(label.rsplit("_", 1)[1])


def to_grid(segments: list[SpeakerSegment], duration: float) -> np.ndarray:
    speakers = max((speaker_index(s.speaker) for s in segments), default=0) + 1
    grid = np.zeros((math.ceil(duration / FRAME_SECONDS), speakers), dtype=np.float32)
    for s in segments:
        grid[int(s.start / FRAME_SECONDS) : math.ceil(s.end / FRAME_SECONDS), speaker_index(s.speaker)] = 1.0
    return grid
