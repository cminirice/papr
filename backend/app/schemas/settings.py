from typing import Literal
from pydantic import Field, StrictInt, model_validator
from app.schemas.common import DTO, BeijingDatetime
from app.schemas.releases import Reason

SettingKey = Literal['question_count_options', 'generation_limits', 'retention_policy']


class CountSetting(DTO):
    choice: list[StrictInt] = Field(default_factory=lambda: [3,6,8,10,12], max_length=5)
    fill: list[StrictInt] = Field(default_factory=lambda: [3,6,8,10,12], max_length=5)
    answer: list[StrictInt] = Field(default_factory=lambda: [3,6,8,10,12], max_length=5)

    @model_validator(mode='after')
    def valid_counts(self):
        for kind in ('choice', 'fill', 'answer'):
            values = getattr(self, kind)
            if len(set(values)) != len(values) or not set(values) <= {3,6,8,10,12}:
                raise ValueError('题量只能选择不重复的3、6、8、10、12；空列表表示关闭此题型')
            setattr(self, kind, sorted(values))
        return self


class GenerationSetting(DTO):
    queue_limit: StrictInt = Field(default=10, ge=1, le=100)
    ip_accept_limit: StrictInt = Field(default=12, ge=1, le=120)


class RetentionSetting(DTO):
    enabled: Literal[False] = False


SettingValue = CountSetting | GenerationSetting | RetentionSetting


class SettingEdit(DTO):
    value: SettingValue
    schema_version: Literal[1]
    reason: Reason


class SettingView(DTO):
    key: SettingKey
    value: SettingValue
    schema_version: Literal[1] = 1
    lock_version: int
    updated_at: BeijingDatetime | None


class SettingList(DTO):
    items: list[SettingView]
