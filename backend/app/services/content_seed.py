"""受控首批草稿导入：只创建或核对，不更新现有内容，不发布。"""
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import write_transaction
from app.generators.multiplication import OBJECTIVE, build_question, supports, verify_question
from app.generators.registry import definition
from app.models.content import (
    CatalogKnowledge, CatalogNode, ContentCatalog, ContentSource, GeneratorDefinition,
    KnowledgePoint, KnowledgeRevision, ObjectiveRevision, QuestionTemplate,
    TemplateObjective, TemplateProfile, TemplateTestCase, TemplateVersion, TrainingObjective,
)
from app.models.identity import AdminUser
from app.schemas.content import MultiplicationParams, MultiplicationProfile

ROOT = Path(__file__).resolve().parents[3]
NAMESPACE = UUID('ab616af2-c250-5b73-b96e-eb9ea85f78ed')


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value) -> str:
    return sha256(canonical(value).encode()).hexdigest()


def stable_id(key: str) -> str:
    return str(uuid5(NAMESPACE, key))


def load_seed():
    seed = json.loads((ROOT / 'content/seeds/mul-vertical-v1.json').read_text())
    registry = definition()
    if (seed['status'], seed['template_code'], seed['objective_code'], seed['render_mode']) != (
        'draft', 'MUL_VERTICAL', OBJECTIVE, 'vertical'
    ) or (seed['generator_key'], seed['generator_version']) != (registry['key'], registry['version']):
        raise ValueError('内置种子与生成器契约不匹配')
    profiles = {p['difficulty']: MultiplicationProfile.model_validate(p) for p in seed['profiles']}
    if len(profiles) != len(seed['profiles']) or set(profiles) != {'basic', 'standard'}:
        raise ValueError('首批档位必须为不重复的基础、提高')
    for profile in profiles.values():
        if not supports(objective_code=seed['objective_code'], question_type=seed['question_type'],
                        difficulty=profile.difficulty, profile=profile):
            raise ValueError('不支持该种子配置')
    for index, case in enumerate(seed['fixed_cases']):
        question = build_question(profiles[case['difficulty']], MultiplicationParams(a=case['a'], b=case['b']), seed=f'fixed-{index}')
        verify_question(question, profiles[case['difficulty']])
        if question.answer.value != case['expected']:
            raise ValueError('固定用例不匹配')
    return seed, registry, profiles


def seed_content(engine, username: str, now) -> dict:
    # 文件、schema与数学计算在写事务外完成。
    seed, registry, profiles = load_seed()
    try:
        with write_transaction(engine) as session:
            admin = session.scalar(select(AdminUser).where(AdminUser.username == username, AdminUser.status == 'active'))
            if admin is None:
                raise ValueError('需要已初始化且启用的管理员')
            plan = []

            def row(model, identity_key, **values):
                values['id'] = stable_id(identity_key)
                for column in model.__table__.columns:
                    if column.name in values or column.name in {'created_at', 'updated_at'}:
                        continue
                    if column.default is not None and column.default.is_scalar:
                        values[column.name] = column.default.arg
                    elif column.nullable:
                        values[column.name] = None
                plan.append((model, values))
                return values['id']

            source = row(ContentSource, 'source:candidate-v1', title='四年级数学候选知识目录',
                reference_note=seed['source'], verification_status='reference',
                evidence_note='项目候选资料，尚未核验具体教材版本。')
            catalog = row(ContentCatalog, 'catalog:upper:v1', code=seed['catalog']['code'],
                name=seed['catalog']['name'], term='upper', source_id=source)
            row(ContentCatalog, 'catalog:lower:v1', code='GRADE4_LOWER_CANDIDATE_V1',
                name='四年级数学下册候选目录', term='lower', source_id=source)
            node = row(CatalogNode, 'theme:multiplication:v1', catalog_id=catalog,
                code=seed['catalog']['theme_code'], name=seed['catalog']['theme_name'])
            point = row(KnowledgePoint, 'point:O002', code='O002')
            knowledge_hash = digest(seed['knowledge'])
            revision = row(KnowledgeRevision, 'knowledge:O002:1', point_id=point,
                revision_no=seed['knowledge']['revision'], name=seed['knowledge']['name'],
                definition=seed['knowledge']['definition'], boundary=seed['knowledge']['boundary'],
                source_id=source, content_hash=knowledge_hash, created_by=admin.id)
            row(CatalogKnowledge, 'mapping:O002:1', node_id=node, knowledge_revision_id=revision)
            objective = row(TrainingObjective, 'objective:O002:column', point_id=point, code=OBJECTIVE)
            objective_revision = row(ObjectiveRevision, 'objective:O002:column:1', objective_id=objective,
                revision_no=1, knowledge_revision_id=revision, name='按位计算并正确合并部分积',
                scope=seed['knowledge']['boundary'], success_criteria=canonical(['部分积正确', '十位对齐', '合并结果正确']),
                content_hash=digest({'objective': OBJECTIVE, 'knowledge_hash': knowledge_hash,
                                     'criteria': ['部分积正确', '十位对齐', '合并结果正确']}), created_by=admin.id)
            generator = row(GeneratorDefinition, f"generator:{registry['key']}:{registry['version']}",
                key=registry['key'], version=registry['version'],
                param_schema=canonical(registry['param_schema']), output_schema=canonical(registry['output_schema']),
                supported_render_modes=canonical(registry['supported_render_modes']),
                supported_question_types=canonical(registry['supported_question_types']),
                supported_target_rules=canonical(registry['supported_objectives']),
                supported_difficulties=canonical(registry['supported_difficulties']),
                artifact_hash=registry['artifact_hash'], validator_version=registry['validator_version'], registered_at=now)
            template = row(QuestionTemplate, 'template:MUL_VERTICAL', code='MUL_VERTICAL', name='三位数乘两位数竖式')
            version = row(TemplateVersion, 'template:MUL_VERTICAL:1', template_id=template, version_no=1,
                generator_id=generator, question_type='answer', render_mode='vertical',
                stem_config=canonical({'instruction': '用竖式计算。'}),
                answer_config=canonical({'kind': 'numeric', 'precision_requirement': 'exact_integer'}),
                explanation_config=canonical({'steps': ['ones_partial', 'tens_partial', 'sum']}),
                content_hash=digest({'seed': seed, 'generator': registry}), created_by=admin.id)
            row(TemplateObjective, 'template:MUL_VERTICAL:1:primary', template_version_id=version,
                objective_revision_id=objective_revision)
            for difficulty, profile in profiles.items():
                data = profile.model_dump()
                profile_id = row(TemplateProfile, f'profile:MUL_VERTICAL:1:{difficulty}',
                    template_version_id=version, difficulty=difficulty,
                    param_config=canonical({k: data[k] for k in ('a_min', 'a_max', 'b_min', 'b_max')}),
                    constraint_config=canonical({k: data[k] for k in ('allow_zero', 'max_carry_events')}),
                    layout_config=canonical(data['layout']), semantic_dedupe_rule='O002_ORDERED_FACTORS_V1',
                    max_per_paper=profile.max_per_paper, profile_hash=digest(data))
                for index, case in enumerate(seed['fixed_cases']):
                    if case['difficulty'] == difficulty:
                        row(TemplateTestCase, f'case:MUL_VERTICAL:1:{index}', profile_id=profile_id,
                            code=f'FIXED_{index + 1}', params=canonical({'a': case['a'], 'b': case['b']}),
                            expected_properties=canonical({'answer': case['expected']}))
            pointers = {point: revision, objective: objective_revision}
            created = 0
            for model, values in plan:
                desired = dict(values)
                if values['id'] in pointers:
                    desired['current_revision_id'] = pointers[values['id']]
                existing = session.get(model, values['id'])
                if existing is not None:
                    # registered_at是首次注册时间，重放不能改时间。
                    comparison = {k: v for k, v in desired.items() if k != 'registered_at'}
                    if any(getattr(existing, key) != value for key, value in comparison.items()):
                        raise ValueError(f'已有{model.__tablename__}内容不一致，拒绝覆盖')
                else:
                    session.add(model(**values, created_at=now, updated_at=now))
                    session.flush()  # 插入顺序保证FK；当前指针最后设置。
                    created += 1
            for model, identity in ((KnowledgePoint, point), (TrainingObjective, objective)):
                session.get(model, identity).current_revision_id = pointers[identity]
            return {'created': created, 'unchanged': len(plan) - created, 'template_id': template,
                    'template_version_id': version, 'status': 'draft'}
    except IntegrityError as exc:
        raise ValueError('种子与现有唯一编码或外键冲突；整批未写入') from exc
