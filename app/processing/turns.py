from app.schemas.transcript import Turn

# When two people talk over each other, OpenAI can return their words as alternating fragments a few tenths
# of a second long. Inside such a run each speaker's fragments are put back together before merging.
FRAGMENT_SECONDS = 1.0
FRAGMENT_JOIN_SECONDS = 0.2


def is_fragment(turn: Turn) -> bool:
    return turn.duration <= FRAGMENT_SECONDS


def group_fragments(turns: list[Turn]) -> list[Turn]:
    result = []
    run = []

    def flush():
        speakers = list(dict.fromkeys(t.speaker for t in run))
        if len(run) >= 3 and len(speakers) > 1:
            run.sort(key=lambda t: speakers.index(t.speaker))
        result.extend(run)
        run.clear()

    for turn in turns:
        if run and not (is_fragment(turn) and turn.start - max(t.end for t in run) <= FRAGMENT_JOIN_SECONDS):
            flush()
        if is_fragment(turn):
            run.append(turn)
        else:
            result.append(turn)
    flush()
    return result


def merge_turns(turns: list[Turn], max_gap: float) -> list[Turn]:
    merged = []
    for turn in group_fragments(sorted(turns, key=lambda t: t.start)):
        last = merged[-1] if merged else None
        if last and last.speaker == turn.speaker and turn.start - last.end <= max_gap:
            merged[-1] = last.model_copy(update={"start": min(last.start, turn.start), "end": max(last.end, turn.end), "text": f"{last.text} {turn.text}"})
        else:
            merged.append(turn)
    return merged
