import uuid
from datetime import datetime
from pydantic import BaseModel


class AssessmentOut(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    episode_id: uuid.UUID | None
    title: str | None
    questions: list
    pass_threshold: int

    model_config = {"from_attributes": True}


class AttemptCreate(BaseModel):
    answers: dict  # {question_index: selected_option_index}


class AttemptOut(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    score: int | None
    passed: bool | None
    attempted_at: datetime

    model_config = {"from_attributes": True}
