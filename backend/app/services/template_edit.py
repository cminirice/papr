"""首个乘法草稿的受控编辑；计算在锁外，最终短事务重验会话和版本。"""
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.security import check_csrf
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.generators.multiplication import OBJECTIVE, build_question, verify_question, template_spec, target_for
from app.generators.registry import definition
from app.models.content import (GeneratorDefinition, KnowledgePoint, KnowledgeRevision, ObjectiveRevision, TrainingObjective,
    QuestionTemplate, TemplateObjective, TemplateProfile, TemplateTestCase, TemplateVersion)
from app.schemas.content import MultiplicationProfile
from app.schemas.template_edit import DraftDetail, DraftEdit, FixedCaseInput
from app.services.content_seed import canonical, digest
from app.services.identity.sessions import require_admin
from app.models.validation import ValidationRun


def find_version(session, identity):
    version = session.get(TemplateVersion, str(identity))
    if version is None:
        raise ServiceError(404, 'NOT_FOUND', '模板版本不存在')
    return version


def snapshot(session, version):
    generator = session.get(GeneratorDefinition, version.generator_id)
    links = session.scalars(select(TemplateObjective).where(TemplateObjective.template_version_id == version.id)).all()
    targets = []
    for link in links:
        revision = session.get(ObjectiveRevision, link.objective_revision_id)
        objective = session.get(TrainingObjective, revision.objective_id)
        knowledge = session.get(KnowledgeRevision, revision.knowledge_revision_id)
        point = session.get(KnowledgePoint, knowledge.point_id)
        targets.append({'id': revision.id, 'role': link.role, 'code': objective.code,
                        'revision_no': revision.revision_no, 'hash': revision.content_hash,
                        'knowledge_revision_id': revision.knowledge_revision_id,
                        'knowledge_hash': knowledge.content_hash, 'knowledge_code': point.code,
                        'knowledge_revision_no': knowledge.revision_no,
                        'same_point': objective.point_id == knowledge.point_id})
    return {
        'hash_schema': 1, 'question_type': version.question_type, 'render_mode': version.render_mode,
        'content_schema_version': version.content_schema_version,
        'stem_config': json.loads(version.stem_config), 'answer_config': json.loads(version.answer_config),
        'explanation_config': json.loads(version.explanation_config),
        'diagram_config': json.loads(version.diagram_config) if version.diagram_config else None,
        'generator': {'id': generator.id, 'key': generator.key, 'version': generator.version,
                      'artifact_hash': generator.artifact_hash, 'validator_version': generator.validator_version},
        'targets': sorted(targets, key=lambda item: item['id']),
    }, generator


def profiles_and_cases(session, version):
    profiles = session.scalars(select(TemplateProfile).where(TemplateProfile.template_version_id == version.id)
                              .order_by(TemplateProfile.difficulty)).all()
    cases = session.scalars(select(TemplateTestCase).where(TemplateTestCase.profile_id.in_([p.id for p in profiles]))
                           .order_by(TemplateTestCase.code)).all()
    if any(p.semantic_dedupe_rule != 'O002_ORDERED_FACTORS_V1' for p in profiles) or any(
        c.kind != 'fixed' or not c.enabled or c.seed is not None or c.params is None for c in cases
    ):
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '当前编辑器仅支持既有乘法规则和显式固定用例')
    return profiles, cases


def detail(session, version, deployed):
    fixed, generator = snapshot(session, version)
    profiles, cases = profiles_and_cases(session, version)
    profile_map = {p.id: p.difficulty for p in profiles}
    config = DraftEdit(profiles=[MultiplicationProfile(
        **json.loads(p.param_config), **json.loads(p.constraint_config), difficulty=p.difficulty,
        max_per_paper=p.max_per_paper, layout=json.loads(p.layout_config)) for p in profiles],
        test_cases=[FixedCaseInput(code=c.code, difficulty=profile_map[c.profile_id],
            params=json.loads(c.params), expected_answer=json.loads(c.expected_properties)['answer']) for c in cases])
    try:
        require_editable(session, version, fixed, generator, deployed, version.lock_version)
        editable = True
    except ServiceError:
        editable = False
    return DraftDetail(id=version.id, template_id=version.template_id, version_no=version.version_no,
        status=version.status, question_type=version.question_type, lock_version=version.lock_version, content_hash=version.content_hash,
        updated_at=version.updated_at, generator_key=generator.key, generator_version=generator.version,
        objective_code=fixed['targets'][0]['code'] if fixed['targets'] else '',
        editable=editable, config=config)


def require_editable(session, version, fixed, generator, deployed, expected):
    if version.lock_version != expected:
        raise ServiceError(409, 'EDIT_CONFLICT', '草稿已被修改，请重新加载后再保存')
    template = session.get(QuestionTemplate, version.template_id)
    if version.status != 'draft' or template.current_published_version_id == version.id:
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '已发布或退役版本不能修改，请创建新草稿')
    if (generator.deployment_status != 'available' or generator.artifact_hash != deployed['artifact_hash']
            or generator.key != deployed['key'] or generator.version != deployed['version']
            or generator.validator_version != deployed['validator_version']
            or json.loads(generator.param_schema) != deployed['param_schema']
            or json.loads(generator.output_schema) != deployed['output_schema']):
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '生成器不可用或部署指纹不一致')
    task = fixed['stem_config'].get('task', 'product')
    knowledge_code, objective_code = target_for(task)
    if (fixed['question_type'], fixed['render_mode'], fixed['content_schema_version']) not in {('answer', 'vertical', 1), ('fill', 'direct', 1), ('choice', 'direct', 1), ('fill', 'vertical', 1), ('choice', 'vertical', 1)} \
            or len(fixed['targets']) != 1 or fixed['targets'][0]['code'] != objective_code \
            or fixed['targets'][0]['role'] != 'primary' or fixed['targets'][0]['revision_no'] != 1 \
            or fixed['targets'][0]['knowledge_code'] != knowledge_code \
            or fixed['targets'][0]['knowledge_revision_no'] != 1 or not fixed['targets'][0]['same_point']:
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '当前编辑器仅支持首个乘法模板')
    task = fixed['stem_config'].get('task', 'product')
    try:
        mode, stem_config = template_spec(task, version.question_type)
    except ValueError as exc:
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '训练内容与题型不匹配') from exc
    if (fixed['render_mode'] != mode or fixed['stem_config'] != stem_config
            or fixed['answer_config'] != ({'kind': 'single_choice'} if version.question_type == 'choice' else {'kind': 'numeric', 'precision_requirement': 'exact_integer'})
            or fixed['explanation_config'] != {'steps': ['ones_partial', 'tens_partial', 'sum']}
            or fixed['diagram_config'] is not None):
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '题干或解析配置与当前生成器不兼容')


def save_draft(engine, identity, body: DraftEdit, expected: int, token: str | None, csrf: str | None, now):
    deployed = definition()
    with Session(engine) as session:
        version = find_version(session, identity)
        fixed, generator = snapshot(session, version)
        require_editable(session, version, fixed, generator, deployed, expected)
        profiles, _ = profiles_and_cases(session, version)
        if {p.difficulty for p in profiles} != {p.difficulty for p in body.profiles}:
            raise ServiceError(422, 'INVALID_CONFIG', '本轮编辑须保留已有难度档位')
    # 仅校验至多30个固定用例，随机批量/容量检查留给worker。
    if any(p.task != fixed['stem_config'].get('task', 'product') for p in body.profiles):
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '不能在编辑草稿时改变训练内容')
    by_difficulty = {p.difficulty: p for p in body.profiles}
    try:
        for case in body.test_cases:
            profile = by_difficulty[case.difficulty]
            question = build_question(profile, case.params, seed=case.code, question_type=fixed['question_type'])
            verify_question(question, profile)
            if question.answer.value != case.expected_answer:
                raise ValueError('固定用例预期答案错误')
    except ValueError as exc:
        raise ServiceError(422, 'INVALID_CONFIG', '固定用例答案或参数不符合难度配置') from exc
    normalized = body.model_dump(mode='json')
    normalized['profiles'].sort(key=lambda p: p['difficulty'])
    normalized['test_cases'].sort(key=lambda c: (c['difficulty'], c['code']))
    new_hash = digest({'fixed': fixed, 'editable': normalized,
                       'semantic_dedupe_rule': 'O002_ORDERED_FACTORS_V1'})
    with write_transaction(engine) as session:
        _, stored = require_admin(session, token, now)
        check_csrf(csrf, stored.csrf_hash)
        version = find_version(session, identity)
        current, generator = snapshot(session, version)
        require_editable(session, version, current, generator, deployed, expected)
        if current != fixed:
            raise ServiceError(409, 'EDIT_CONFLICT', '关联配置已变化，请重新加载')
        profiles, cases = profiles_and_cases(session, version)
        for profile in profiles:
            new = by_difficulty[profile.difficulty].model_dump()
            profile.param_config = canonical({k: new[k] for k in ('a_min', 'a_max', 'b_min', 'b_max', 'task')})
            profile.constraint_config = canonical({k: new[k] for k in ('allow_zero', 'max_carry_events')})
            profile.layout_config = canonical(new['layout'])
            profile.max_per_paper = new['max_per_paper']
            profile.profile_hash = digest(new)
            profile.validated_count_options = '[]'
            profile.updated_at = now
        ids = {p.difficulty: p.id for p in profiles}
        old = {(c.profile_id, c.code): c for c in cases}
        for item in body.test_cases:
            key = (ids[item.difficulty], item.code)
            case = old.pop(key, None)
            if case is None:
                case = TemplateTestCase(profile_id=key[0], code=key[1], created_at=now)
                session.add(case)
            case.params = canonical(item.params.model_dump())
            case.expected_properties = canonical({'answer': item.expected_answer})
            case.kind, case.seed, case.enabled = 'fixed', None, 1
            case.updated_at = now
        for obsolete in old.values():
            session.delete(obsolete)
        version.content_hash = new_hash
        for run in session.scalars(select(ValidationRun).where(ValidationRun.template_version_id == version.id)):
            run.status = 'stale'
            run.updated_at = now
        version.lock_version += 1
        version.updated_at = now
        session.get(QuestionTemplate, version.template_id).updated_at = now
        session.flush()
        return detail(session, version, deployed)
