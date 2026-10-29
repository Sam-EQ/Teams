import math
from itertools import groupby

import numpy as np

from app.core.config import FRAME_SECONDS
from app.schemas.transcript import Word

SENTENCE_END = (".", "?", "!")


def speaker_of(word: Word, probs: np.ndarray, threshold: float) -> str | None:
    first = int(word.start / FRAME_SECONDS)
    last = max(first + 1, math.ceil(word.end / FRAME_SECONDS))
    window = probs[first:last]
    if not len(window):
        return None
    scores = window.mean(axis=0)
    best = int(scores.argmax())
    return f"speaker_{best}" if scores[best] >= threshold else None


def fill_speakers(labels: list[str | None]) -> list[str]:
    known = [label for label in labels if label]
    if not known:
        return ["speaker_0"] * len(labels)
    filled = []
    last = known[0]
    for label in labels:
        last = label or last
        filled.append(last)
    return filled


def smooth(words: list[Word], max_words: int) -> list[Word]:
    runs = [list(run) for _, run in groupby(words, key=lambda w: w.speaker)]
    for i in range(1, len(runs) - 1):
        before, run, after = runs[i - 1], runs[i], runs[i + 1]
        if len(run) <= max_words and before[0].speaker == after[0].speaker and not run[-1].text.endswith(SENTENCE_END):
            runs[i] = [w.model_copy(update={"speaker": before[0].speaker}) for w in run]
    return [w for run in runs for w in run]


def assign(words: list[Word], probs: np.ndarray, threshold: float, max_words: int) -> list[Word]:
    labels = fill_speakers([speaker_of(w, probs, threshold) for w in words])
    labelled = [w.model_copy(update={"speaker": s}) for w, s in zip(words, labels)]
    return smooth(labelled, max_words)
