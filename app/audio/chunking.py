from dataclasses import dataclass
from pathlib import Path

from app.audio.convert import cut


@dataclass
class Chunk:
    path: Path
    start: float
    end: float


def plan_cuts(duration: float, silences: list[float], target: float, window: float, max_length: float) -> list[float]:
    cuts = []
    position = 0.0
    while duration - position > max_length:
        goal = position + target
        near = [s for s in silences if goal - window <= s <= goal + window]
        position = min(near, key=lambda s: abs(s - goal)) if near else goal
        cuts.append(position)
    return cuts


def split_audio(wav: Path, out_dir: Path, duration: float, cuts: list[float]) -> list[Chunk]:
    if not cuts:
        return [Chunk(path=wav, start=0.0, end=duration)]
    out_dir.mkdir(parents=True, exist_ok=True)
    bounds = [0.0, *cuts, duration]
    return [
        Chunk(path=cut(wav, out_dir / f"chunk_{index:03d}.wav", start, end), start=start, end=end)
        for index, (start, end) in enumerate(zip(bounds, bounds[1:]))
    ]
