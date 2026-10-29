from app.processing.names import match_names
from app.schemas.transcript import SpeakerSegment, Turn, Word


def reference(word: Word, cues: list[SpeakerSegment]) -> str | None:
    middle = (word.start + word.end) / 2
    names = {c.speaker for c in cues if c.start <= middle <= c.end}
    return names.pop() if len(names) == 1 else None


def teams_agreement(words: list[Word], turns: list[Turn], cues: list[SpeakerSegment], min_seconds: float) -> dict | None:
    if not cues:
        return None
    names = match_names(cues, turns, min_seconds)
    scored = [(names.get(w.speaker), ref) for w in words if (ref := reference(w, cues))]
    if not scored:
        return None
    correct = sum(1 for guess, ref in scored if guess == ref)
    return {"words": len(scored), "correct": correct, "accuracy": round(correct / len(scored), 4)}
