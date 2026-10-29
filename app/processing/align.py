import re
from difflib import SequenceMatcher

from app.schemas.transcript import Word


def normalize(token: str) -> str:
    return re.sub(r"[^\w]", "", token.lower())


def fill_times(times: list[tuple[float, float] | None], start: float, end: float) -> list[tuple[float, float]]:
    filled = list(times)
    i = 0
    while i < len(filled):
        if filled[i] is not None:
            i += 1
            continue
        j = i
        while j < len(filled) and filled[j] is None:
            j += 1
        left = filled[i - 1][1] if i else start
        right = filled[j][0] if j < len(filled) else end
        step = max(right - left, 0.0) / (j - i)
        for k in range(i, j):
            filled[k] = (left + step * (k - i), left + step * (k - i + 1))
        i = j
    return filled


def align_words(text: str, anchors: list[Word], start: float, end: float) -> list[Word]:
    tokens = text.split()
    if not tokens:
        return []
    times = [None] * len(tokens)
    matcher = SequenceMatcher(None, [normalize(t) for t in tokens], [normalize(a.text) for a in anchors], autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            anchor = anchors[block.b + k]
            times[block.a + k] = (anchor.start, anchor.end)
    return [Word(start=s, end=e, text=t) for t, (s, e) in zip(tokens, fill_times(times, start, end))]


def align_chunks(chunks: list[dict], anchors: list[Word]) -> list[Word]:
    words = []
    for i, chunk in enumerate(chunks):
        last = i == len(chunks) - 1
        own = [a for a in anchors if chunk["start"] <= a.start and (last or a.start < chunk["end"])]
        words += align_words(chunk["text"], own, chunk["start"], chunk["end"])
    return words
