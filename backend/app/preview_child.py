"""Bounded, deterministic preview in an isolated child; no database access."""
import json
import sys
from app.generators.registry import definition
from app.generators.multiplication import generate_paper
from app.schemas.content import MultiplicationProfile


def preview(payload):
    if payload['artifact_hash'] != definition()['artifact_hash']:
        raise ValueError('Generator changed')
    profile = MultiplicationProfile.model_validate(payload['profile'])
    return generate_paper(profile, seed=payload['request']['seed'], count=payload['request']['count'],
                          question_type=payload['fixed']['question_type'])


if __name__ == '__main__':
    questions = preview(json.load(sys.stdin))
    print(json.dumps([q.model_dump(mode='json') for q in questions], ensure_ascii=False))
