import re
import subprocess
from pathlib import Path

PATTERN = re.compile(r"silence_(start|end): (-?[\d.]+)")


def parse_silences(log: str) -> list[float]:
    points = []
    start = None
    for kind, value in PATTERN.findall(log):
        if kind == "start":
            start = max(float(value), 0.0)
        elif start is not None:
            points.append((start + float(value)) / 2)
            start = None
    return points


def find_silences(path: Path, noise_db: float, min_seconds: float) -> list[float]:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", f"silencedetect=noise={noise_db}dB:d={min_seconds}", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_silences(result.stderr)
