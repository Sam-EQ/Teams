from pydantic import BaseModel, field_serializer


class Timed(BaseModel):
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    @field_serializer("start", "end")
    def round_time(self, value: float) -> float:
        return round(value, 2)


class TextSegment(Timed):
    text: str
    label: str | None = None


class SpeakerSegment(Timed):
    speaker: str


class Turn(Timed):
    speaker: str
    text: str


class NamedTurn(Turn):
    name: str


class TranscriptView(BaseModel):
    speakers: dict[str, str]
    turns: list[NamedTurn]
