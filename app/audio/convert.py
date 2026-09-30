import subprocess
from pathlib import Path

import numpy as np

from app.core.config import SAMPLE_RATE

FFMPEG = ["ffmpeg", "-y", "-loglevel", "error"]
MONO_16K = ["-vn", "-ac", "1", "-ar", str(SAMPLE_RATE)]


def to_wav(src: Path, dst: Path) -> Path:
    subprocess.run([*FFMPEG, "-i", str(src), *MONO_16K, "-c:a", "pcm_s16le", str(dst)], check=True)
    return dst


def cut(src: Path, dst: Path, start: float, end: float) -> Path:
    subprocess.run(
        [*FFMPEG, "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(src), *MONO_16K, "-c:a", "pcm_s16le", str(dst)],
        check=True,
    )
    return dst


def load_samples(path: Path) -> np.ndarray:
    result = subprocess.run([*FFMPEG, "-i", str(path), *MONO_16K, "-f", "f32le", "pipe:1"], capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.float32)
