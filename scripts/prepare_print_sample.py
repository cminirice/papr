"""Prepare a mathematically checked, offline sample; no database or production content changes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.time import beijing_now, serialize_time
from app.generators.multiplication import generate_paper
from app.schemas.content import MultiplicationProfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, choices=[3, 6, 8, 10, 12], default=12)
    parser.add_argument('--difficulty', choices=['basic', 'standard'], default='standard')
    parser.add_argument('--questions-per-row', type=int, choices=[1, 2, 3, 4, 5], default=2)
    parser.add_argument('--solutions-per-row', type=int, choices=[1, 2, 3, 4, 5], default=1)
    args = parser.parse_args()
    seed = json.loads((ROOT / 'content/seeds/mul-vertical-v1.json').read_text())
    profile = MultiplicationProfile.model_validate(next(p for p in seed['profiles'] if p['difficulty'] == args.difficulty))
    profile.layout.questions_per_row = args.questions_per_row
    profile.layout.solutions_per_row = args.solutions_per_row
    questions = generate_paper(profile, seed='papr-print-sample-v1', count=args.count)
    document = {'schema_version': 1, 'title': '纸上练 · 乘法练习（开发样张）',
                'generated_at': serialize_time(beijing_now()), 'questions': [q.model_dump(mode='json') for q in questions]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print('已生成经数学校验的开发输入；尚未渲染或验收PDF')


if __name__ == '__main__':
    main()
