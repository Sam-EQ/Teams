from openai import AsyncOpenAI

from app.core.config import MINUTES_MODEL
from app.schemas.minutes import Minutes
from app.schemas.transcript import Turn

INSTRUCTIONS = """You write minutes of meeting from a speaker-labelled transcript.
Use only what is said in the transcript. Do not invent facts, owners or dates.
title: a short title for the meeting.
summary: 3 to 6 sentences.
key_points: the main topics discussed.
decisions: things that were agreed. Empty list if none.
action_items: owner is the speaker label or name responsible, task is what they will do, due is the deadline as said or an empty string.
open_questions: things raised but not resolved.
speaker_suggestions: only for the unnamed speakers listed. Suggest a real name only when the transcript makes it clear, for example someone is addressed by name right before they reply. evidence is the short quote that shows it. Empty list if unsure."""


def clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def empty_minutes() -> Minutes:
    return Minutes(title="No speech detected", summary="", key_points=[], decisions=[], action_items=[], open_questions=[], speaker_suggestions=[])


class MinutesWriter:
    def __init__(self, client: AsyncOpenAI):
        self.client = client

    async def write(self, turns: list[Turn], names: dict[str, str]) -> Minutes:
        if not turns:
            return empty_minutes()
        unnamed = sorted({t.speaker for t in turns} - set(names))
        transcript = "\n".join(f"[{clock(t.start)}] {names.get(t.speaker, t.speaker)}: {t.text}" for t in turns)
        response = await self.client.responses.parse(
            model=MINUTES_MODEL,
            instructions=INSTRUCTIONS,
            input=f"Unnamed speakers: {', '.join(unnamed) or 'none'}\n\nTranscript:\n{transcript}",
            text_format=Minutes,
        )
        if response.output_parsed is None:
            raise RuntimeError("minutes model returned no structured output")
        return response.output_parsed
