from itertools import groupby

from app.processing.assign import overlap
from app.schemas.transcript import SpeakerSegment, TextSegment


def speech_regions(speakers: list[SpeakerSegment], join_seconds: float) -> list[SpeakerSegment]:
    regions = []
    ordered = sorted(speakers, key=lambda s: (s.speaker, s.start))
    for _, group in groupby(ordered, key=lambda s: s.speaker):
        for s in group:
            last = regions[-1] if regions else None
            if last and last.speaker == s.speaker and s.start - last.end <= join_seconds:
                regions[-1] = last.model_copy(update={"end": max(last.end, s.end)})
            else:
                regions.append(s)
    return sorted(regions, key=lambda r: r.start)


def coverage(region: SpeakerSegment, segments: list[TextSegment]) -> float:
    return sum(overlap(region, s) for s in segments) / region.duration


def find_gaps(
    speakers: list[SpeakerSegment],
    segments: list[TextSegment],
    min_seconds: float,
    max_coverage: float,
    join_seconds: float,
) -> list[SpeakerSegment]:
    candidates = [
        r for r in speech_regions(speakers, join_seconds)
        if r.duration >= min_seconds and coverage(r, segments) <= max_coverage
    ]
    gaps = []
    for region in sorted(candidates, key=lambda r: r.duration, reverse=True):
        if all(overlap(region, g) < region.duration / 2 for g in gaps):
            gaps.append(region)
    return sorted(gaps, key=lambda g: g.start)
