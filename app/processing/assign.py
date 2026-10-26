from collections import defaultdict

from app.schemas.transcript import SpeakerSegment, TextSegment, Timed, Turn

# OpenAI's speaker labels are too coarse to name speakers (it often merges two people into one label),
# but they still say which Nemotron speakers a segment can belong to, and where the speaker changes.
LABEL_FLOOR = 0.05
LABEL_MIN_SHARE = 0.2
LABEL_FALLBACK_SHARE = 0.5
INTERJECTION_SECONDS = 2.0
NEIGHBOUR_SECONDS = 2.0


def overlap(a: Timed, b: Timed) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def distance(a: Timed, b: Timed) -> float:
    return max(b.start - a.end, a.start - b.end, 0.0)


def overlaps(segment: TextSegment, speakers: list[SpeakerSegment]) -> dict[str, float]:
    totals = defaultdict(float)
    for s in speakers:
        if (o := overlap(segment, s)) > 0:
            totals[s.speaker] += o
    return totals


def label_shares(segments: list[TextSegment], speakers: list[SpeakerSegment]) -> dict[str, dict[str, float]]:
    """For each OpenAI label, the share of its speech time each Nemotron speaker overlaps."""
    counts = defaultdict(lambda: defaultdict(float))
    for segment in segments:
        for speaker, seconds in overlaps(segment, speakers).items():
            counts[segment.label][speaker] += seconds
    return {label: {s: v / sum(c.values()) for s, v in c.items()} for label, c in counts.items()}


def assign_speaker(segment: TextSegment, speakers: list[SpeakerSegment], shares: dict[str, dict[str, float]] | None = None) -> str | None:
    """None when Nemotron heard nothing during the segment, see fill_silent."""
    if not speakers:
        return "speaker_0"
    share = (shares or {}).get(segment.label, {})
    totals = overlaps(segment, speakers)
    if not totals:
        return None
    return max(totals, key=lambda s: totals[s] * (LABEL_FLOOR + share.get(s, 0.0)))


def fill_silent(segments: list[TextSegment], speakers: list[SpeakerSegment], shares: dict, assigned: list[str | None]) -> list[str]:
    """Segments Nemotron heard no speech in follow the nearest segment with the same OpenAI label, then the label's
    main speaker, then the nearest Nemotron speaker."""
    result = list(assigned)
    for i, segment in enumerate(segments):
        if result[i] is not None:
            continue
        same = [
            j for j in range(len(segments))
            if assigned[j] is not None and segments[j].label == segment.label and distance(segment, segments[j]) <= NEIGHBOUR_SECONDS
        ]
        share = shares.get(segment.label, {})
        if same:
            result[i] = assigned[min(same, key=lambda j: distance(segment, segments[j]))]
        elif share and max(share.values()) >= LABEL_FALLBACK_SHARE:
            result[i] = max(share, key=share.get)
        else:
            result[i] = min(speakers, key=lambda s: distance(segment, s)).speaker
    return result


def split_interjections(segments: list[TextSegment], speakers: list[SpeakerSegment], shares: dict, assigned: list[str]) -> list[str]:
    """A short segment whose OpenAI label differs from both neighbours is someone cutting in, so it should not
    go to the person being interrupted when another plausible speaker overlaps it."""
    result = list(assigned)
    for i in range(1, len(segments) - 1):
        before, segment, after = segments[i - 1], segments[i], segments[i + 1]
        if segment.duration > INTERJECTION_SECONDS or segment.label in (None, before.label) or before.label != after.label:
            continue
        host = assigned[i - 1]
        if assigned[i + 1] != host or assigned[i] != host:
            continue
        share = shares.get(segment.label, {})
        others = {s: v for s, v in overlaps(segment, speakers).items() if s != host and share.get(s, 0.0) >= LABEL_MIN_SHARE}
        if others:
            result[i] = max(others, key=others.get)
    return result


def assign(segments: list[TextSegment], speakers: list[SpeakerSegment]) -> list[Turn]:
    shares = label_shares(segments, speakers)
    assigned = fill_silent(segments, speakers, shares, [assign_speaker(s, speakers, shares) for s in segments])
    assigned = split_interjections(segments, speakers, shares, assigned)
    return [Turn(start=s.start, end=s.end, speaker=speaker, text=s.text) for s, speaker in zip(segments, assigned)]
