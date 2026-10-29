from dataclasses import dataclass
from pathlib import Path

from app.core.config import DIARIZATION_THRESHOLD, NAME_MIN_SECONDS, SMOOTH_MAX_WORDS, TURN_GAP_SECONDS
from app.processing.assign import assign
from app.processing.names import match_names, parse_vtt
from app.processing.score import teams_agreement
from app.processing.turns import build_turns
from app.schemas.transcript import SpeakerSegment, Turn, Word
from app.services.diarization import Diarization


@dataclass
class Stitched:
    words: list[Word]
    turns: list[Turn]
    names: dict[str, str]
    agreement: dict | None


def read_cues(work: Path) -> list[SpeakerSegment]:
    vtt = work / "teams.vtt"
    return parse_vtt(vtt.read_text()) if vtt.exists() else []


def stitch(words: list[Word], diarization: Diarization, cues: list[SpeakerSegment]) -> Stitched:
    words = assign(words, diarization.probs, DIARIZATION_THRESHOLD, SMOOTH_MAX_WORDS)
    turns = build_turns(words, TURN_GAP_SECONDS)
    names = match_names(cues, turns, NAME_MIN_SECONDS) if cues else {}
    return Stitched(words=words, turns=turns, names=names, agreement=teams_agreement(words, turns, cues, NAME_MIN_SECONDS))
