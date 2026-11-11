from copy import deepcopy
import json
from pathlib import Path
from random import Random

from pydantic import ValidationError
import pytest

from app.generators.multiplication import (
    OBJECTIVE, GenerationError, accepts, build_question, capacity, carry_events,
    generate_paper, sample_params, supports, verify_question,
)
from app.generators.registry import definition
from app.schemas.content import MultiplicationParams, MultiplicationProfile, MultiplicationQuestion

SEED = json.loads((Path(__file__).resolve().parents[2] / 'content/seeds/mul-vertical-v1.json').read_text())


@pytest.fixture
def profiles():
    return {p['difficulty']: MultiplicationProfile.model_validate(p) for p in SEED['profiles']}


@pytest.mark.parametrize('case', SEED['fixed_cases'])
def test_fixed_answers_and_partial_place_values(profiles, case):
    profile = profiles[case['difficulty']]
    question = build_question(profile, MultiplicationParams(a=case['a'], b=case['b']), seed='fixed')
    assert question.answer.value == case['expected']
    assert int(question.render_spec.ones_partial) + int(question.render_spec.tens_partial) == int(case['expected'])
    assert int(question.render_spec.tens_partial) % 10 == 0
    verify_question(question, profile)


def test_boundaries_and_profile_contract(profiles):
    for a, b in [(100, 11), (109, 19), (308, 26), (999, 99)]:
        assert accepts(profiles['standard'], MultiplicationParams(a=a, b=b))
    for a, b in [(100, 11), (109, 19), (308, 26), (999, 99)]:
        with pytest.raises(GenerationError, match='难度约束'):
            build_question(profiles['basic'], MultiplicationParams(a=a, b=b), seed='bad')
    for a, b in [(101, 10), (99, 11), (1000, 11), (100, 100), (True, 11), ('123', 12)]:
        with pytest.raises(ValidationError):
            MultiplicationParams(a=a, b=b)
    for changes in [{'allow_zero': True}, {'a_max': 999}, {'max_carry_events': 3},
                    {'difficulty': 'challenge'}, {'a_min': 299, 'a_max': 100}]:
        with pytest.raises(ValidationError):
            MultiplicationProfile.model_validate(profiles['basic'].model_dump() | changes)
    assert carry_events(123, 12) == 0
    assert carry_events(199, 19) == 5  # 个位乘法3次、合并部分积2次。
    assert carry_events(999, 99) == 9


@pytest.mark.parametrize('difficulty', ['basic', 'standard'])
def test_determinism_roundtrip_and_whole_papers(profiles, difficulty):
    profile = profiles[difficulty]
    for count in (3, 6, 8, 10, 12):
        for index in range(20):
            questions = generate_paper(profile, seed=f'paper-{index}', count=count)
            assert questions == generate_paper(profile, seed=f'paper-{index}', count=count)
            assert len({(q.render_spec.multiplicand, q.render_spec.multiplier) for q in questions}) == count
            assert [q.position for q in questions] == list(range(1, count + 1))
            for question in questions:
                assert MultiplicationQuestion.model_validate_json(question.model_dump_json()) == question
    assert generate_paper(profile, seed='one', count=12) != generate_paper(profile, seed='two', count=12)


def test_verifier_detects_corruption(profiles):
    profile = profiles['standard']
    question = build_question(profile, MultiplicationParams(a=308, b=26), seed='corruption')
    original = question.model_dump(mode='json')
    variants = []
    for field in ('ones_partial', 'tens_partial', 'result'):
        data = deepcopy(original)
        data['render_spec'][field] = '616'  # 错位十位部分积。
        variants.append(data)
    data = deepcopy(original)
    data['answer']['value'] = '2464'
    variants.append(data)
    data = deepcopy(original)
    data['stem_blocks'][1]['latex'] = '308×25='
    variants.append(data)
    data = deepcopy(original)
    data['explanation_steps'][2]['blocks'][1]['latex'] = '1848+616=2464'
    variants.append(data)
    data = deepcopy(original)
    data['layout']['answer_space_mm'] = 36
    variants.append(data)
    for data in variants:
        with pytest.raises(GenerationError) as error:
            verify_question(MultiplicationQuestion.model_validate(data), profile)
        assert error.value.code == 'INVALID_CONTENT'
    for field, value in [('schema_version', 2), ('render_spec', {'kind': 'html', 'html': '<script/>'}),
                         ('stem_blocks', [{'type': 'unknown', 'text': 'hidden'}])]:
        with pytest.raises(ValidationError):
            MultiplicationQuestion.model_validate(original | {field: value})


def test_real_capacity_and_finite_exhaustion(profiles):
    # 独立枚举无进位的小空间：111..113 × 11..12，共6种。
    narrow = MultiplicationProfile(difficulty='basic', a_min=111, a_max=113,
        b_min=11, b_max=12, allow_zero=False, max_carry_events=0)
    assert capacity(narrow) == 6
    assert len(generate_paper(narrow, seed='six', count=6)) == 6
    with pytest.raises(GenerationError) as error:
        generate_paper(narrow, seed='too-many', count=8)
    assert error.value.code == 'GENERATION_EXHAUSTED'
    empty = narrow.model_copy(update={'a_min': 100, 'a_max': 100})
    assert capacity(empty) == 0
    with pytest.raises(GenerationError):
        sample_params(empty, Random(42))
    with pytest.raises(GenerationError):
        generate_paper(empty, seed='empty', count=1)
    assert capacity(profiles['standard']) == 900 * 89
    for count in (True, 0, 13, '3'):
        with pytest.raises(GenerationError) as error:
            generate_paper(narrow, seed='invalid', count=count)
        assert error.value.code == 'INVALID_CONFIG'


def test_registry_support_is_not_publication(profiles):
    definition_a = definition()
    assert len(definition_a['artifact_hash']) == 64
    definition_a['supported_difficulties'].append('unsupported')
    assert definition()['supported_difficulties'] == ['basic', 'standard', 'challenge']
    assert SEED['status'] == 'draft'
    assert supports(objective_code=OBJECTIVE, question_type='answer', difficulty='basic', profile=profiles['basic'])
    for changes in ({'objective_code': 'O003'}, {'question_type': 'unsupported'}, {'difficulty': 'challenge'}):
        assert not supports(**({'objective_code': OBJECTIVE, 'question_type': 'answer',
                              'difficulty': 'basic', 'profile': profiles['basic']} | changes))


def test_basic_capacity_with_independent_carry_oracle(profiles):
    def oracle(a, b):
        # 直接用低位前缀判断跨列进位，不复用逐位循环及 carry 状态。
        product_carries = sum(
            ((a % 10**k) * digit) // 10**k > 0
            for digit in (b % 10, b // 10) for k in range(1, 4)
        )
        left, right = a * (b % 10), a * (b // 10) * 10
        addition_carries = sum((left % 10**k + right % 10**k) >= 10**k for k in range(1, 6))
        return product_carries + addition_carries
    expected_capacity = 0
    for a in range(100, 300):
        for b in range(11, 20):
            expected = oracle(a, b)
            assert carry_events(a, b) == expected
            expected_capacity += int('0' not in f'{a}{b}' and expected <= 2)
    assert capacity(profiles['basic']) == expected_capacity
