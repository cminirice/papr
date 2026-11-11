"""首个竖式模板的严格内容契约；尚未实现的题型不接受宽泛 JSON。"""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, model_validator

from app.schemas.common import DTO


class TextBlock(DTO):
    type: Literal['text'] = 'text'
    text: str = Field(min_length=1, max_length=500)


class MathBlock(DTO):
    type: Literal['math'] = 'math'
    latex: str = Field(min_length=1, max_length=200)


ContentBlock = Annotated[TextBlock | MathBlock, Field(discriminator='type')]


class NumericAnswer(DTO):
    kind: Literal['numeric'] = 'numeric'
    value: str = Field(pattern=r'^(0|[1-9][0-9]*)$')
    unit: None = None
    precision_requirement: Literal['exact_integer'] = 'exact_integer'


class ChoiceOption(DTO):
    id: UUID
    value: str = Field(min_length=1, max_length=100)


class ChoiceAnswer(DTO):
    kind: Literal['single_choice'] = 'single_choice'
    value: str = Field(min_length=1, max_length=100)
    correct_option_id: UUID


class ExplanationStep(DTO):
    blocks: list[ContentBlock] = Field(min_length=1, max_length=4)


class QuestionLayout(DTO):
    questions_per_row: StrictInt = Field(default=2, ge=1, le=5)
    solutions_per_row: StrictInt = Field(default=1, ge=1, le=5)
    answer_space_mm: StrictInt = Field(default=35, ge=20, le=100)
    keep_together: Literal[True] = True
    diagram_size_mm: None = None


class MultiplicationParams(DTO):
    a: StrictInt = Field(ge=100, le=999)
    b: StrictInt = Field(ge=11, le=99)


class VerticalMultiplication(DTO):
    incorrect_tens_partial: str | None = Field(default=None, pattern=r'^(0|[1-9][0-9]*)$')
    incorrect_result: str | None = Field(default=None, pattern=r'^(0|[1-9][0-9]*)$')
    missing_digit_index: Literal[1] | None = None
    kind: Literal['integer_multiplication'] = 'integer_multiplication'
    multiplicand: str = Field(pattern=r'^[1-9][0-9]{2}$')
    multiplier: str = Field(pattern=r'^[1-9][0-9]$')
    ones_partial: str = Field(pattern=r'^(0|[1-9][0-9]*)$')
    tens_partial: str = Field(pattern=r'^(0|[1-9][0-9]*)$')
    tens_shift: Literal[1] = 1
    result: str = Field(pattern=r'^[1-9][0-9]*$')


class MultiplicationQuestion(DTO):
    schema_version: Literal[1] = 1
    id: UUID
    position: StrictInt = Field(ge=1, le=36)
    question_type: Literal['answer', 'fill', 'choice'] = 'answer'
    render_mode: Literal['vertical', 'direct'] = 'vertical'
    difficulty: Literal['basic', 'standard', 'challenge']
    primary_knowledge_code: Literal['O002', 'O003'] = 'O002'
    stem_blocks: list[ContentBlock] = Field(min_length=1, max_length=4)
    options: list[ChoiceOption] = Field(default_factory=list, max_length=4)
    answer: Annotated[NumericAnswer | ChoiceAnswer, Field(discriminator='kind')]
    explanation_steps: list[ExplanationStep] = Field(min_length=3, max_length=3)
    layout: QuestionLayout
    render_spec: VerticalMultiplication


    @model_validator(mode='after')
    def compatible_presentation(self):
        if (self.question_type, self.render_mode) not in {('answer', 'vertical'), ('fill', 'direct'), ('choice', 'direct'), ('fill', 'vertical'), ('choice', 'vertical')}:
            raise ValueError('题型与呈现形式不兼容')
        missing = self.render_spec.missing_digit_index is not None
        incorrect = self.render_spec.incorrect_tens_partial is not None
        if incorrect != (self.render_spec.incorrect_result is not None) or (incorrect and missing):
            raise ValueError('错误过程字段不完整或与挖空冲突')
        if incorrect != (self.question_type in ('choice', 'answer') and self.render_mode == 'vertical' and self.difficulty == 'challenge'):
            raise ValueError('错误原因题型不匹配')
        if missing != (self.question_type == 'fill' and self.render_mode == 'vertical') or (missing or incorrect) != (self.difficulty == 'challenge'):
            raise ValueError('缺数填空呈现或难度不匹配')
        if self.question_type == 'choice':
            if (not isinstance(self.answer, ChoiceAnswer) or len(self.options) != 4
                    or len({o.id for o in self.options}) != 4 or len({o.value for o in self.options}) != 4
                    or sum(o.id == self.answer.correct_option_id and o.value == self.answer.value for o in self.options) != 1):
                raise ValueError('选择题须有四个不同选项和唯一正确选项')
        elif self.options or not isinstance(self.answer, NumericAnswer):
            raise ValueError('非选择题不能带选项或选择答案')
        return self


class MultiplicationProfile(DTO):
    task: Literal['product', 'missing_digit', 'error_choice', 'correction', 'zero_product'] = 'product'
    difficulty: Literal['basic', 'standard', 'challenge']
    a_min: StrictInt = Field(ge=100, le=999)
    a_max: StrictInt = Field(ge=100, le=999)
    b_min: StrictInt = Field(ge=11, le=99)
    b_max: StrictInt = Field(ge=11, le=99)
    allow_zero: StrictBool
    max_carry_events: StrictInt = Field(ge=0, le=9)
    max_per_paper: StrictInt = Field(default=12, ge=1, le=12)
    layout: QuestionLayout = Field(default_factory=QuestionLayout)

    @model_validator(mode='after')
    def ranges_and_difficulty(self):
        if (self.task in ('missing_digit', 'error_choice', 'correction')) != (self.difficulty == 'challenge'):
            raise ValueError('推理任务仅支持挑战档，普通求积仅支持基础/提高')
        if self.task == 'zero_product' and (self.difficulty != 'standard' or not self.allow_zero):
            raise ValueError('含零因数训练仅支持提高档且必须允许零')
        if self.a_min > self.a_max or self.b_min > self.b_max:
            raise ValueError('参数下界不能超过上界')
        if self.difficulty == 'basic' and (
            self.a_max > 299 or self.b_max > 19 or self.allow_zero
            or self.max_carry_events > 2
        ):
            raise ValueError('基础档仅支持100–299、11–19、无零且最多2次进位')
        return self
