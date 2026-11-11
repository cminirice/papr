"""Bounded math worker protocol; no database or filesystem writes."""
import json
import sys
from app.schemas.paper_jobs import PaperPlan
from app.generators.multiplication import generate_paper

if __name__ == '__main__':
    plan = PaperPlan.model_validate_json(sys.stdin.read(1024 * 1024))
    from app.generators.multiplication import semantic_signature
    from app.schemas.content import MultiplicationParams
    questions, seen = [], set()
    for part in plan.allocations():
        generated = generate_paper(part.profile, seed=part.seed, count=part.request.question_type_counts.total,
                                   question_type=part.fixed['question_type'], excluded_signatures=seen)
        for question in generated:
            question.position = len(questions) + 1
            questions.append(question)
            seen.add(semantic_signature(MultiplicationParams(a=int(question.render_spec.multiplicand), b=int(question.render_spec.multiplier))))
    print(json.dumps([q.model_dump(mode='json') for q in questions], ensure_ascii=False))
