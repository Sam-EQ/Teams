from app.schemas.transcript import Turn, Word


def build_turns(words: list[Word], max_gap: float) -> list[Turn]:
    groups = []
    for word in words:
        last = groups[-1][-1] if groups else None
        if last and last.speaker == word.speaker and word.start - last.end <= max_gap:
            groups[-1].append(word)
        else:
            groups.append([word])
    return [
        Turn(start=g[0].start, end=g[-1].end, speaker=g[0].speaker, text=" ".join(w.text for w in g))
        for g in groups
    ]
