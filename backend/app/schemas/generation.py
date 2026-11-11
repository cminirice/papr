from typing import Literal
from uuid import UUID
from pydantic import Field, StrictInt, model_validator
from app.schemas.common import DTO

Difficulty = Literal["basic", "standard", "challenge"]
QuestionType = Literal["choice", "fill", "answer"]
JobPhase = Literal["queued", "generating", "rendering", "saving", "done"]


class QuestionCounts(DTO):
    choice: StrictInt = Field(ge=0, le=12)
    fill: StrictInt = Field(ge=0, le=12)
    answer: StrictInt = Field(ge=0, le=12)

    @property
    def total(self) -> int:
        return self.choice + self.fill + self.answer


class CreatePaperJob(DTO):
    theme_id: UUID
    knowledge_point_ids: list[UUID] = Field(min_length=1, max_length=10)
    difficulty: Difficulty
    question_type_counts: QuestionCounts
    content_epoch: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def validate_selection(self):
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError("知识点不能重复")
        if self.question_type_counts.total < len(self.knowledge_point_ids):
            raise ValueError("题量不足以覆盖每个知识点")
        return self
