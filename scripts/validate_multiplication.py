"""离线开发验证；不创建 validation_run、不审题、不发布、不接触运行数据库。"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.time import beijing_now, serialize_time
from app.generators.multiplication import (
    COUNT_OPTIONS, build_question, capacity, generate_paper, supports, verify_question,
)
from app.generators.registry import definition
from app.schemas.content import MultiplicationParams, MultiplicationProfile


def validate() -> dict:
    seed = json.loads((ROOT / 'content/seeds/mul-vertical-v1.json').read_text())
    registry = definition()
    if (seed['generator_key'], seed['generator_version']) != (registry['key'], registry['version']):
        raise ValueError('种子算法版本与部署不符')
    inputs = {'seed': seed, 'generator': registry}
    input_hash = sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False,
                                  separators=(',', ':')).encode()).hexdigest()
    profiles = {p['difficulty']: MultiplicationProfile.model_validate(p) for p in seed['profiles']}
    report = {'generated_at': serialize_time(beijing_now()), 'input_hash': input_hash,
              'generator_artifact_hash': registry['artifact_hash'],
              'validation_kind': 'offline_development', 'template_status': 'draft',
              'human_review': 'pending', 'pdf_review': 'pending', 'profiles': [], 'samples': []}
    for index, case in enumerate(seed['fixed_cases']):
        profile = profiles[case['difficulty']]
        question = build_question(profile, MultiplicationParams(a=case['a'], b=case['b']), seed=f'fixed-{index}')
        verify_question(question, profile)
        if question.answer.value != case['expected']:
            raise ValueError('固定样例答案不一致')
        report['samples'].append(question.model_dump(mode='json'))
    for profile in profiles.values():
        if not supports(objective_code=seed['objective_code'], question_type=seed['question_type'],
                        difficulty=profile.difficulty, profile=profile):
            raise ValueError('配置组合不受生成器支持')
        actual_capacity = capacity(profile)
        for index in range(100):
            generate_paper(profile, seed=f'random-{index}', count=1)
        checked_options = []
        for count in COUNT_OPTIONS:
            if count > min(actual_capacity, profile.max_per_paper):
                continue
            for index in range(20):
                questions = generate_paper(profile, seed=f'paper-{count}-{index}', count=count)
                signatures = {(q.render_spec.multiplicand, q.render_spec.multiplier) for q in questions}
                if len(signatures) != count:
                    raise ValueError('整卷出现重复')
            checked_options.append(count)
        report['profiles'].append({'difficulty': profile.difficulty, 'exact_capacity': actual_capacity,
            'random_cases': 100, 'papers_per_count': 20, 'checked_count_options': checked_options})
    report['result'] = 'passed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='可选报告路径；默认输出到终端')
    args = parser.parse_args()
    result = json.dumps(validate(), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
        print(f'离线数学验证通过；报告：{args.output}；人工审题与PDF待完成。')
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
