from pydantic import BaseModel


class ActionItem(BaseModel):
    owner: str
    task: str
    due: str


class SpeakerSuggestion(BaseModel):
    speaker_id: str
    name: str
    evidence: str


class Minutes(BaseModel):
    title: str
    summary: str
    key_points: list[str]
    decisions: list[str]
    action_items: list[ActionItem]
    open_questions: list[str]
    speaker_suggestions: list[SpeakerSuggestion]
