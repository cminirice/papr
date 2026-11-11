"""独立受控子进程，只读stdin快照并输出JSON；不连接数据库。"""
import json
import sys
from app.generators.multiplication import COUNT_OPTIONS, build_question, capacity, generate_paper, verify_question
from app.generators.registry import definition
from app.schemas.template_edit import DraftEdit
from app.schemas.validation import FailureSample, ProfileCoverage, ValidationReport


def validate_payload(payload: dict) -> ValidationReport:
    if payload['policy_version'] != 1 or payload['fixed']['generator']['artifact_hash'] != definition()['artifact_hash']:
        raise ValueError('部署与快照不一致')
    config = DraftEdit.model_validate(payload['config'])
    failures, coverage, samples = [], [], []
    failure_count, sample_count = 0, 0

    def fail(difficulty, error, *, code=None, seed=None, params=None):
        nonlocal failure_count
        failure_count += 1
        if len(failures) < 100:
            failures.append(FailureSample(difficulty=difficulty, case_code=code, seed=seed, params=params,
                error_code=getattr(error, 'code', 'INVALID_CONTENT'), message=str(error)[:300]))

    for profile in config.profiles:
        for case in config.test_cases:
            if case.difficulty != profile.difficulty:
                continue
            try:
                question = build_question(profile, case.params, seed=case.code, question_type=payload['fixed']['question_type'])
                verify_question(question, profile)
                if question.answer.value != case.expected_answer:
                    raise ValueError('固定用例预期答案不一致')
                sample_count += 1
                samples.append(question)
            except ValueError as error:
                fail(profile.difficulty, error, code=case.code, params=case.params)
        actual_capacity = capacity(profile)
        for index in range(100):
            seed = f'validation-random-{index}'
            try:
                sample_count += len(generate_paper(profile, seed=seed, count=1, question_type=payload['fixed']['question_type']))
            except ValueError as error:
                fail(profile.difficulty, error, seed=seed)
        checked = []
        for count in COUNT_OPTIONS:
            if count > profile.max_per_paper:
                continue
            prior_failures = failure_count
            for index in range(20):
                seed = f'validation-paper-{count}-{index}'
                try:
                    questions = generate_paper(profile, seed=seed, count=count, question_type=payload['fixed']['question_type'])
                    if len({(q.render_spec.multiplicand, q.render_spec.multiplier) for q in questions}) != count:
                        raise ValueError('整卷出现重复题目')
                    sample_count += len(questions)
                except ValueError as error:
                    fail(profile.difficulty, error, seed=seed)
            if failure_count == prior_failures:
                checked.append(count)
        if not checked:
            fail(profile.difficulty, ValueError('没有通过验证的候选题量'))
        coverage.append(ProfileCoverage(difficulty=profile.difficulty, exact_capacity=actual_capacity,
                         random_cases=100, papers_per_count=20, checked_count_options=checked))
    return ValidationReport(result='failed' if failure_count else 'passed', sample_count=sample_count,
        failure_count=failure_count, failures_truncated=failure_count > len(failures), coverage=coverage,
        failures=failures, samples=samples)


if __name__ == '__main__':
    result = validate_payload(json.load(sys.stdin))
    print(result.model_dump_json())
