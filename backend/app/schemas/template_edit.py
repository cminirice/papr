from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.schemas.common import BeijingDatetime, DTO
from app.schemas.content import MultiplicationParams, MultiplicationProfile


class FixedCaseInput(DTO):
    code: str = Field(pattern=r'^[A-Z][A-Z0-9_]{0,63}$')
    difficulty: Literal['basic', 'standard', 'challenge']
    params: MultiplicationParams
    expected_answer: str = Field(min_length=1, max_length=100)


class DraftEdit(DTO):
    profiles: list[MultiplicationProfile] = Field(min_length=1, max_length=2)
    test_cases: list[FixedCaseInput] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def unique_and_covered(self):
        difficulties = {profile.difficulty for profile in self.profiles}
        if len(difficulties) != len(self.profiles):
            raise ValueError('难度配置不能重复')
        keys = {(case.difficulty, case.code) for case in self.test_cases}
        if len(keys) != len(self.test_cases):
            raise ValueError('同档固定用例编码不能重复')
        if {case.difficulty for case in self.test_cases} != difficulties:
            raise ValueError('每档须有固定用例，且不能引用不存在的档位')
        return self


class VersionSummary(DTO):
    id: UUID
    version_no: int
    status: Literal['draft', 'published', 'retired']
    lock_version: int
    content_hash: str
    updated_at: BeijingDatetime


class TemplateDetail(DTO):
    id: UUID
    name: str
    code: str
    versions: list[VersionSummary]


class DraftDetail(VersionSummary):
    question_type: Literal['answer', 'fill', 'choice'] = 'answer'
    template_id: UUID
    generator_key: str
    generator_version: str
    objective_code: str
    editable: bool
    config: DraftEdit
