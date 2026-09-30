import json
import subprocess
from pathlib import Path

from app.core.errors import InvalidMedia


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index:format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise InvalidMedia("file is not a readable audio or video file")
    info = json.loads(result.stdout or "{}")
    if not info.get("streams"):
        raise InvalidMedia("file has no audio stream")
    try:
        return float(info["format"]["duration"])
    except (KeyError, ValueError):
        raise InvalidMedia("could not read media duration")
