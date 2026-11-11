"""integer_multiplication_v1：确定性采样、有限重试和独立数学校验。"""
from hashlib import sha256
import json
from random import Random
from uuid import UUID, uuid5

from app.schemas.content import (
    ChoiceAnswer, ChoiceOption, ExplanationStep, MathBlock, MultiplicationParams, MultiplicationProfile,
    MultiplicationQuestion, NumericAnswer, TextBlock, VerticalMultiplication,
)

KEY = 'integer_multiplication_v1'
VERSION = '1.0.0'
VALIDATOR_VERSION = '1.0.0'
OBJECTIVE = 'O002_COLUMN_MULTIPLY_V1'
ZERO_OBJECTIVE = 'O003_ZERO_MULTIPLY_V1'

def target_for(task):
    return ('O003', ZERO_OBJECTIVE) if task == 'zero_product' else ('O002', OBJECTIVE)
NAMESPACE = UUID('b9de80f8-d662-5a6a-a717-4fbb9a693f67')
COUNT_OPTIONS = (3, 6, 8, 10, 12)
ERROR_REASONS = ('十位部分积没有按十位对齐', '个位乘法算错了', '乘数的十位数字看错了', '两个部分积相加算错了')


def template_spec(task, kind):
    if task in ('product', 'zero_product') and kind in ('answer', 'fill', 'choice'):
        return ('vertical' if kind == 'answer' else 'direct', ({'task': task} if task == 'zero_product' else {}) | {'instruction': {
            'answer': '用竖式计算。', 'fill': '计算乘积，填入括号。', 'choice': '选择正确的乘积。'}[kind]})
    if (task, kind) in {('missing_digit', 'fill'), ('error_choice', 'choice'), ('correction', 'answer')}:
        return ('vertical', {'task': task, 'instruction': '在方框里填上合适的数字。' if task == 'missing_digit' else ('下面竖式哪里出错了？选择正确的原因。' if task == 'error_choice' else '指出下面竖式的错误，说明原因并写出正确的竖式。')})
    raise GenerationError('INVALID_CONFIG', '训练内容与题型不匹配')



class GenerationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_config(value: MultiplicationProfile | dict) -> MultiplicationProfile:
    # Revalidate model instances too: callers may have used model_copy(update=...).
    if isinstance(value, MultiplicationProfile):
        value = value.model_dump()
    return MultiplicationProfile.model_validate(value)


def supports(*, objective_code: str, question_type: str, difficulty: str,
             profile: MultiplicationProfile) -> bool:
    try:
        profile = validate_config(profile)
    except ValueError:
        return False
    return (objective_code == target_for(profile.task)[1] and question_type in ('answer', 'fill', 'choice')
            and difficulty == profile.difficulty
            and (profile.task in ('product', 'zero_product') or (profile.task, question_type) in {('missing_digit', 'fill'), ('error_choice', 'choice'), ('correction', 'answer')}))


def carry_events(a: int, b: int) -> int:
    """每列产生非零向高位进位记一次，包含两部分积及最终加法。"""
    events = 0
    for digit in (b % 10, b // 10):
        carry = 0
        for char in reversed(str(a)):
            carry = (int(char) * digit + carry) // 10
            events += int(carry > 0)
    left, right, carry = a * (b % 10), a * (b // 10) * 10, 0
    while left or right:
        carry = (left % 10 + right % 10 + carry) // 10
        events += int(carry > 0)
        left //= 10
        right //= 10
    return events


def accepts(profile: MultiplicationProfile, params: MultiplicationParams) -> bool:
    a, b = params.a, params.b
    return (profile.a_min <= a <= profile.a_max
            and profile.b_min <= b <= profile.b_max
            and (profile.task != 'zero_product' or '0' in f'{a}{b}')
            and (profile.allow_zero or '0' not in f'{a}{b}')
            and carry_events(a, b) <= profile.max_carry_events)


def sample_params(profile: MultiplicationProfile, rng: Random) -> MultiplicationParams:
    for _ in range(50):
        params = MultiplicationParams(a=rng.randint(profile.a_min, profile.a_max),
                                      b=rng.randint(profile.b_min, profile.b_max))
        if accepts(profile, params):
            return params
    raise GenerationError('GENERATION_EXHAUSTED', '50次采样未找到合法参数')


def semantic_signature(params: MultiplicationParams) -> str:
    return f'{OBJECTIVE}:vertical:{params.a}:{params.b}'


def render_spec(params: MultiplicationParams) -> VerticalMultiplication:
    a, b = params.a, params.b
    return VerticalMultiplication(multiplicand=str(a), multiplier=str(b),
        ones_partial=str(a * (b % 10)), tens_partial=str(a * (b // 10) * 10),
        result=str(a * b))


def build_question(profile: MultiplicationProfile, params: MultiplicationParams,
                   *, seed: str, position: int = 1, question_type: str = 'answer') -> MultiplicationQuestion:
    if question_type not in ('answer', 'fill', 'choice'):
        raise GenerationError('INVALID_CONFIG', '不支持的题型')
    profile = validate_config(profile)
    params = MultiplicationParams.model_validate(params.model_dump())
    if not accepts(profile, params):
        raise GenerationError('INVALID_CONFIG', '参数不满足指定难度约束')
    a, b = params.a, params.b
    mode, stem_config = template_spec(profile.task, question_type)
    spec = render_spec(params)
    if profile.task == 'missing_digit':
        spec.missing_digit_index = 1
    if profile.task in ('error_choice', 'correction'):
        spec.incorrect_tens_partial = str(a * (b // 10))
        spec.incorrect_result = str(a * (b % 10) + a * (b // 10))
    steps = [
        ('先算个位上的数与被乘数的积。', rf'{a}\times {b % 10}={spec.ones_partial}'),
        ('再算十位上的数与被乘数的积，按十位对齐。', rf'{a}\times {b // 10}\times 10={spec.tens_partial}'),
        ('把两个部分积相加。', f'{spec.ones_partial}+{spec.tens_partial}={spec.result}'),
    ]
    identity = json.dumps([VERSION, seed, position, profile.model_dump(), semantic_signature(params), question_type],
                          sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    if profile.task == 'missing_digit':
        digit = str(a)[1]
        steps[0] = (f'把0到9逐个试填，只有{digit}使乘积等于{spec.result}。', rf'{a}\times {b}={spec.result}')
    if profile.task in ('error_choice', 'correction'):
        steps[1] = ('十位部分积没有按十位对齐，应把第二行部分积左移一位。', rf'{a}\times {b // 10}\times 10={spec.tens_partial}')
    question_id = uuid5(NAMESPACE, identity)
    options = []
    answer = NumericAnswer(value=str(a)[1] if profile.task == 'missing_digit' else spec.result)
    if question_type == 'choice':
        # Each distractor corresponds to a concrete partial-product/place-value error.
        ones, tens = int(spec.ones_partial), int(spec.tens_partial)
        values = [int(spec.result)]
        for wrong in (ones + tens // 10, ones, tens, ones + tens * 10):
            if wrong not in values:
                values.append(wrong)
            if len(values) == 4:
                break
        if profile.task == 'error_choice':
            values = list(ERROR_REASONS)
        options = [ChoiceOption(id=uuid5(question_id, str(value)), value=str(value)) for value in values]
        answer = ChoiceAnswer(value=options[0].value, correct_option_id=options[0].id)
        Random(int.from_bytes(sha256(identity.encode()).digest(), 'big')).shuffle(options)
    return MultiplicationQuestion(id=question_id, position=position,
        difficulty=profile.difficulty, primary_knowledge_code=target_for(profile.task)[0], question_type=question_type,
        render_mode=mode,
        stem_blocks=([TextBlock(text='在方框里填上合适的数字。'), MathBlock(latex=rf'{str(a)[0]}□{str(a)[2]}\times {b}={spec.result}')] if profile.task == 'missing_digit' else [TextBlock(text=stem_config['instruction']),
                     MathBlock(latex=rf'{a}\times {b}=' + ('( )' if question_type == 'fill' else ''))]),
        answer=answer, options=options, render_spec=spec,
        explanation_steps=[ExplanationStep(blocks=[TextBlock(text=text), MathBlock(latex=math)])
                           for text, math in steps], layout=profile.layout.model_copy(deep=True))


def verify_question(question: MultiplicationQuestion, profile: MultiplicationProfile) -> None:
    """用重复加法检查部分积/结果，不调用生成器答案或展示构造函数。"""
    question = MultiplicationQuestion.model_validate(question.model_dump())
    profile = validate_config(profile)
    spec = question.render_spec
    a, b = int(spec.multiplicand), int(spec.multiplier)
    params = MultiplicationParams(a=a, b=b)
    if not accepts(profile, params) or question.difficulty != profile.difficulty or question.primary_knowledge_code != target_for(profile.task)[0]:
        raise GenerationError('INVALID_CONTENT', '题目不符合难度约束')
    ones = sum(a for _ in range(b % 10))
    tens = sum(a for _ in range(b - b % 10))
    total = sum(a for _ in range(b))
    if question.question_type == 'choice' and profile.task in ('product', 'zero_product'):
        values = {int(o.value) for o in question.options}
        allowed_wrong = {ones + tens // 10, ones, tens, ones + tens * 10} - {total}
        if total not in values or not (values - {total}) <= allowed_wrong:
            raise GenerationError('INVALID_CONTENT', '选择题干扰项与位值或部分积错误不一致')
    expected_answer = str(total)
    if profile.task in ('error_choice', 'correction'):
        expected_answer = '十位部分积没有按十位对齐' if profile.task == 'error_choice' else str(total)
        if (question.question_type != ('choice' if profile.task == 'error_choice' else 'answer') or spec.incorrect_tens_partial != str(sum(a for _ in range(b // 10)))
                or spec.incorrect_result != str(ones + tens // 10)
                or (profile.task == 'error_choice' and set(o.value for o in question.options) != {'十位部分积没有按十位对齐', '个位乘法算错了', '乘数的十位数字看错了', '两个部分积相加算错了'})):
            raise GenerationError('INVALID_CONTENT', '给定错误过程或原因选项不一致')
    elif spec.incorrect_result is not None or spec.incorrect_tens_partial is not None:
        raise GenerationError('INVALID_CONTENT', '非辨错题不能带错误过程')
    if profile.task == 'missing_digit':
        candidates = [d for d in range(10) if sum((a // 100 * 100 + d * 10 + a % 10) for _ in range(b)) == total]
        if len(candidates) != 1 or spec.missing_digit_index != 1:
            raise GenerationError('INVALID_CONTENT', '缺数题必须有唯一填法')
        expected_answer = str(candidates[0])
    elif spec.missing_digit_index is not None:
        raise GenerationError('INVALID_CONTENT', '普通求积题不能挖空')
    expected_steps = [
        [('text', '先算个位上的数与被乘数的积。'), ('math', rf'{a}\times {b % 10}={ones}')],
        [('text', '再算十位上的数与被乘数的积，按十位对齐。'), ('math', rf'{a}\times {b // 10}\times 10={tens}')],
        [('text', '把两个部分积相加。'), ('math', f'{ones}+{tens}={total}')],
    ]
    if profile.task == 'missing_digit':
        expected_steps[0] = [('text', f'把0到9逐个试填，只有{expected_answer}使乘积等于{total}。'), ('math', rf'{a}\times {b}={total}')]
    if profile.task in ('error_choice', 'correction'):
        expected_steps[1] = [('text', '十位部分积没有按十位对齐，应把第二行部分积左移一位。'), ('math', rf'{a}\times {b // 10}\times 10={tens}')]
    expected_stem = [('text', '用竖式计算。' if question.question_type == 'answer' else ('计算乘积，填入括号。' if question.question_type == 'fill' else '选择正确的乘积。')),
                     ('math', rf'{a}\times {b}=' + ('( )' if question.question_type == 'fill' else ''))]
    if profile.task == 'missing_digit':
        if question.question_type != 'fill':
            raise GenerationError('INVALID_CONTENT', '缺数任务题型错误')
        expected_stem = [('text', '在方框里填上合适的数字。'), ('math', rf'{str(a)[0]}□{str(a)[2]}\times {b}={total}')]
    if profile.task == 'error_choice':
        expected_stem[0] = ('text', '下面竖式哪里出错了？选择正确的原因。')
    if profile.task == 'correction':
        expected_stem[0] = ('text', '指出下面竖式的错误，说明原因并写出正确的竖式。')
    def blocks_value(blocks):
        return [(block.type, block.text if isinstance(block, TextBlock) else block.latex)
                for block in blocks]
    if (spec.ones_partial != str(ones) or spec.tens_partial != str(tens)
            or spec.result != str(total) or question.answer.value != expected_answer
            or blocks_value(question.stem_blocks) != expected_stem
            or [blocks_value(step.blocks) for step in question.explanation_steps] != expected_steps
            or question.layout != profile.layout):
        raise GenerationError('INVALID_CONTENT', '题干、部分积、答案、解析或留白不一致')


def generate_paper(profile: MultiplicationProfile, *, seed: str, count: int, question_type: str = 'answer', excluded_signatures: set[str] | None = None) -> list[MultiplicationQuestion]:
    profile = validate_config(profile)
    if type(count) is not int or not 1 <= count <= profile.max_per_paper:
        raise GenerationError('INVALID_CONFIG', '题量超出模板上限')
    if not isinstance(seed, str) or not 1 <= len(seed) <= 128:
        raise GenerationError('INVALID_CONFIG', 'seed需为1–128字符字符串')
    rng = Random(int.from_bytes(sha256(f'{KEY}:{VERSION}:{seed}'.encode()).digest(), 'big'))
    seen, questions = set(excluded_signatures or ()), []
    candidate_attempts = 0
    # 每轮仅采样一次，总次数不会与单候选50次相乘。
    for _ in range(max(200, count * 50)):
        candidate_attempts += 1
        params = MultiplicationParams(a=rng.randint(profile.a_min, profile.a_max),
                                      b=rng.randint(profile.b_min, profile.b_max))
        signature = semantic_signature(params)
        if not accepts(profile, params) or signature in seen:
            if candidate_attempts >= 50:
                raise GenerationError('GENERATION_EXHAUSTED', '单候选50次尝试未获得合法且不重复的题目')
            continue
        question = build_question(profile, params, seed=seed, position=len(questions) + 1, question_type=question_type)
        verify_question(question, profile)
        questions.append(question)
        seen.add(signature)
        candidate_attempts = 0
        if len(questions) == count:
            return questions
    raise GenerationError('GENERATION_EXHAUSTED', '有限采样内无法满足去重题量')


def capacity(profile: MultiplicationProfile) -> int:
    """精确枚举当前有限参数空间；不在 API 请求或数据库写锁内调用。"""
    profile = validate_config(profile)
    return sum(accepts(profile, MultiplicationParams(a=a, b=b))
               for a in range(profile.a_min, profile.a_max + 1)
               for b in range(profile.b_min, profile.b_max + 1))
