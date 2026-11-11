import json
from sqlalchemy import select
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.generators.registry import definition
from app.generators.multiplication import OBJECTIVE, build_question, verify_question, template_spec, ERROR_REASONS, ZERO_OBJECTIVE, target_for
from app.models.content import (GeneratorDefinition, KnowledgePoint, KnowledgeRevision, TrainingObjective,
    ObjectiveRevision, QuestionTemplate, TemplateVersion, TemplateObjective, TemplateProfile, TemplateTestCase)
from app.schemas.template_edit import DraftEdit
from app.schemas.template_tools import GeneratorChoice
from app.services.capabilities import get
from app.services.content_seed import canonical, digest
from app.services.releases import actor, audit
from app.services.template_edit import detail, snapshot, require_editable


def default_config(task='product'):
    if task == 'zero_product':
        data = default_config().model_dump()
        data['profiles'] = [p | {'task': task} for p in data['profiles'] if p['difficulty'] == 'standard']
        data['test_cases'] = [{'code': 'ZERO_FACTOR', 'difficulty': 'standard', 'params': {'a': 308, 'b': 26}, 'expected_answer': '8008'}]
        return DraftEdit.model_validate(data)
    if task in ('missing_digit', 'error_choice', 'correction'):
        return DraftEdit.model_validate({'profiles': [{'task': task, 'difficulty': 'challenge',
            'a_min': 100, 'a_max': 999, 'b_min': 11, 'b_max': 99, 'allow_zero': True, 'max_carry_events': 9}],
            'test_cases': [{'code': 'MISSING_TENS', 'difficulty': 'challenge', 'params': {'a': 123, 'b': 12}, 'expected_answer': '2' if task == 'missing_digit' else ERROR_REASONS[0] if task == 'error_choice' else '1476'}]})
    return DraftEdit.model_validate({'profiles': [
        {'difficulty': 'basic', 'a_min': 100, 'a_max': 299, 'b_min': 11, 'b_max': 19, 'allow_zero': False, 'max_carry_events': 2},
        {'difficulty': 'standard', 'a_min': 100, 'a_max': 999, 'b_min': 11, 'b_max': 99, 'allow_zero': True, 'max_carry_events': 9}],
        'test_cases': [{'code': 'INITIAL', 'difficulty': d, 'params': {'a': 123, 'b': 12}, 'expected_answer': '1476'} for d in ('basic', 'standard')]})


def choices(session):
    deployed = definition()
    targets = session.scalars(select(ObjectiveRevision).join(TrainingObjective,
        TrainingObjective.id == ObjectiveRevision.objective_id).join(KnowledgeRevision,
        KnowledgeRevision.id == ObjectiveRevision.knowledge_revision_id).join(KnowledgePoint,
        KnowledgePoint.id == KnowledgeRevision.point_id).where(TrainingObjective.code.in_([OBJECTIVE, ZERO_OBJECTIVE]),
        TrainingObjective.point_id == KnowledgePoint.id, ObjectiveRevision.revision_no == 1,
        KnowledgeRevision.revision_no == 1, KnowledgePoint.code.in_(['O002', 'O003']))).all()
    result = []
    for row in session.scalars(select(GeneratorDefinition).order_by(GeneratorDefinition.key, GeneratorDefinition.version)):
        available = (row.key == deployed['key'] and row.version == deployed['version']
            and row.artifact_hash == deployed['artifact_hash'] and row.validator_version == deployed['validator_version']
            and row.deployment_status == 'available' and json.loads(row.param_schema) == deployed['param_schema']
            and json.loads(row.output_schema) == deployed['output_schema'])
        result.append(GeneratorChoice(id=row.id, key=row.key, version=row.version, available=available,
            question_types=deployed['supported_question_types'] if available else [],
            difficulties=deployed['supported_difficulties'] if available else [],
            objective_revision_ids=[t.id for t in targets] if available else [], default_config=default_config(), task_objective_revision_ids={task: [t.id for t in targets if session.get(TrainingObjective, t.objective_id).code == target_for(task)[1] and session.get(KnowledgePoint, session.get(KnowledgeRevision, t.knowledge_revision_id).point_id).code == target_for(task)[0]] for task in ('product', 'missing_digit', 'error_choice', 'correction', 'zero_product')}, task_configs={task: default_config(task) for task in ('product', 'missing_digit', 'error_choice', 'correction', 'zero_product')}))
    return result


def create(engine, body, *, token, csrf, now, request_id):
    # At most 30 explicit examples, checked outside the write transaction.
    try:
        mode, stem_config = template_spec(body.task, body.question_type)
    except ValueError as exc:
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '训练内容与题型不匹配') from exc
    if any(p.task != body.task for p in body.config.profiles):
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '训练内容、题型和难度配置不匹配')
    profiles = {p.difficulty: p for p in body.config.profiles}
    for case in body.config.test_cases:
        try:
            question = build_question(profiles[case.difficulty], case.params, seed=case.code, question_type=body.question_type)
            verify_question(question, profiles[case.difficulty])
            if question.answer.value != case.expected_answer:
                raise ValueError('answer mismatch')
        except ValueError as exc:
            raise ServiceError(422, 'INVALID_CONFIG', '固定用例与当前参数或答案不一致') from exc
    deployed = definition()
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        allowed = next((g for g in choices(session) if g.id == body.generator_id and g.available), None)
        if not allowed or body.objective_revision_id not in allowed.task_objective_revision_ids[body.task]:
            raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '生成组件不支持所选目标修订')
        if session.scalar(select(QuestionTemplate).where(QuestionTemplate.code == body.code)):
            raise ServiceError(409, 'INVALID_CONFIG', '模板编码已存在')
        template = QuestionTemplate(code=body.code, name=body.name, created_at=now, updated_at=now)
        session.add(template)
        session.flush()
        version = TemplateVersion(template_id=template.id, version_no=1, generator_id=str(body.generator_id),
            question_type=body.question_type, render_mode=mode, stem_config=canonical(stem_config),
            answer_config=canonical({'kind': 'single_choice'} if body.question_type == 'choice' else {'kind': 'numeric', 'precision_requirement': 'exact_integer'}),
            explanation_config=canonical({'steps': ['ones_partial', 'tens_partial', 'sum']}),
            content_hash='0' * 64, created_by=admin.id, created_at=now, updated_at=now)
        session.add(version)
        session.flush()
        session.add(TemplateObjective(template_version_id=version.id, objective_revision_id=str(body.objective_revision_id),
            role='primary', created_at=now, updated_at=now))
        for profile in body.config.profiles:
            data = profile.model_dump(mode='json')
            row = TemplateProfile(template_version_id=version.id, difficulty=profile.difficulty,
                param_config=canonical({k: data[k] for k in ('a_min', 'a_max', 'b_min', 'b_max', 'task')}),
                constraint_config=canonical({k: data[k] for k in ('allow_zero', 'max_carry_events')}),
                layout_config=canonical(data['layout']), semantic_dedupe_rule='O002_ORDERED_FACTORS_V1',
                max_per_paper=profile.max_per_paper, profile_hash=digest(data), validated_count_options='[]',
                created_at=now, updated_at=now)
            session.add(row)
            session.flush()
            for case in body.config.test_cases:
                if case.difficulty == profile.difficulty:
                    session.add(TemplateTestCase(profile_id=row.id, code=case.code, params=canonical(case.params.model_dump()),
                        expected_properties=canonical({'answer': case.expected_answer}), created_at=now, updated_at=now))
        session.flush()
        fixed, generator = snapshot(session, version)
        require_editable(session, version, fixed, generator, deployed, 1)
        normalized = body.config.model_dump(mode='json')
        normalized['profiles'].sort(key=lambda p: p['difficulty'])
        normalized['test_cases'].sort(key=lambda c: (c['difficulty'], c['code']))
        version.content_hash = digest({'fixed': fixed, 'editable': normalized, 'semantic_dedupe_rule': 'O002_ORDERED_FACTORS_V1'})
        audit(session, admin, 'create', 'question_template', template.id, request_id, body.reason,
              None, {'version_id': version.id, 'content_hash': version.content_hash}, now)
        return detail(session, version, deployed)
