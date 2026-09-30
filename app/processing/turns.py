from app.schemas.transcript import Turn


def merge_turns(turns: list[Turn], max_gap: float) -> list[Turn]:
    merged = []
    for turn in sorted(turns, key=lambda t: t.start):
        last = merged[-1] if merged else None
        if last and last.speaker == turn.speaker and turn.start - last.end <= max_gap:
            merged[-1] = last.model_copy(update={"end": max(last.end, turn.end), "text": f"{last.text} {turn.text}"})
        else:
            merged.append(turn)
    return merged
