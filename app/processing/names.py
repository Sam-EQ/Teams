import re
from collections import defaultdict

from app.schemas.transcript import SpeakerSegment, Timed, Turn

TIMING = re.compile(r"([\d:.]+)\s*-->\s*([\d:.]+)")
VOICE = re.compile(r"<v\s+([^>]+)>")


def overlap(a: Timed, b: Timed) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def seconds(stamp: str) -> float:
    total = 0.0
    for part in stamp.split(":"):
        total = total * 60 + float(part)
    return total


def parse_vtt(text: str) -> list[SpeakerSegment]:
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        timing = TIMING.search(block)
        voice = VOICE.search(block)
        if timing and voice:
            cues.append(SpeakerSegment(start=seconds(timing.group(1)), end=seconds(timing.group(2)), speaker=voice.group(1).strip()))
    return cues


def match_names(cues: list[SpeakerSegment], turns: list[Turn], min_seconds: float) -> dict[str, str]:
    scores = defaultdict(float)
    for cue in cues:
        for turn in turns:
            scores[(turn.speaker, cue.speaker)] += overlap(cue, turn)
    names = {}
    for (speaker, name), score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        if score < min_seconds:
            break
        if speaker not in names and name not in names.values():
            names[speaker] = name
    return names
