from typing import Literal
from uuid import UUID
from pydantic import Field, StrictInt, model_validator
from app.schemas.common import DTO
from app.schemas.generation import Difficulty, QuestionType, QuestionCounts
from app.schemas.releases import Reason


class CatalogState(DTO):
    reason: Reason
    status: Literal['draft', 'active', 'archived']


class NodeState(DTO):
    reason: Reason
    status: Literal['draft', 'active', 'disabled']


class NodeView(DTO):
    id: UUID
    catalog_id: UUID
    code: str
    sort_order: int
    name: str
    parent_id: UUID | None
    node_type: Literal['theme', 'group']
    status: Literal['draft', 'active', 'disabled']
    lock_version: int


class PointView(DTO):
    id: UUID
    code: str
    name: str


class QuantityPolicy(DTO):
    difficulty: Difficulty
    question_type: QuestionType
    count_options: list[StrictInt] = Field(max_length=5)
    default_count: StrictInt | None

    @model_validator(mode='after')
    def valid(self):
        if len(set(self.count_options)) != len(self.count_options) or not set(self.count_options) <= {3,6,8,10,12}:
            raise ValueError('题量须为去重的3、6、8、10、12')
        if self.default_count is not None and self.default_count not in self.count_options:
            raise ValueError('默认题量必须属于配置选项')
        return self


class PolicyEdit(DTO):
    reason: Reason
    policies: list[QuantityPolicy] = Field(min_length=9, max_length=9)

    @model_validator(mode='after')
    def unique(self):
        if len({(p.difficulty, p.question_type) for p in self.policies}) != 9:
            raise ValueError('须提交三档三题型完整矩阵')
        return self


class PolicyCell(QuantityPolicy):
    supported_count_options: list[int]
    effective_count_options: list[int]
    evidence_version_ids: list[UUID]
    unavailable_reason: str | None


class PointCapabilities(DTO):
    point: PointView
    lock_version: int
    policies: list[PolicyCell]


class CapabilitySelection(DTO):
    theme_id: UUID
    knowledge_point_ids: list[UUID] = Field(min_length=1, max_length=10)
    difficulty: Difficulty

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError('知识点不得重复')
        return self


class CountOptions(DTO):
    choice: list[int]
    fill: list[int]
    answer: list[int]


class CapabilityView(DTO):
    content_epoch: int
    selection_hash: str
    count_options: CountOptions
    feasible_counts: list[QuestionCounts]
    point_coverage: list[UUID]
    warnings: list[str]
