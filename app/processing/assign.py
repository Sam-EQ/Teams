from collections import defaultdict

from app.schemas.transcript import SpeakerSegment, TextSegment, Timed, Turn


def overlap(a: Timed, b: Timed) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def distance(a: Timed, b: Timed) -> float:
    return max(b.start - a.end, a.start - b.end, 0.0)


def assign_speaker(segment: TextSegment, speakers: list[SpeakerSegment]) -> str:
    if not speakers:
        return "speaker_0"
    totals = defaultdict(float)
    for s in speakers:
        totals[s.speaker] += overlap(segment, s)
    best = max(totals, key=totals.get)
    if totals[best] > 0:
        return best
    return min(speakers, key=lambda s: distance(segment, s)).speaker


def assign(segments: list[TextSegment], speakers: list[SpeakerSegment]) -> list[Turn]:
    return [Turn(start=s.start, end=s.end, speaker=assign_speaker(s, speakers), text=s.text) for s in segments]
