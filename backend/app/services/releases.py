"""人工审题、前置修订发布和模板发布；所有变更均为短事务及追加审计。"""
import json
from sqlalchemy import select, literal_column, func
from app.auth.security import check_csrf
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.generators.registry import definition
from app.models.content import (KnowledgePoint, KnowledgeRevision, ObjectiveRevision,
    QuestionTemplate, TrainingObjective, TemplateVersion, TemplateProfile, TemplateTestCase, TemplateObjective)
from app.models.jobs import Job
from app.models.releases import AdminOperationLog, ContentRelease, ContentReview
from app.models.system import ContentEpoch
from app.models.validation import ValidationRun
from app.schemas.releases import DependencyView, ReleaseContext, ReleaseView, ReviewView
from app.schemas.validation import ValidationReport
from app.services.content_seed import canonical
from app.services.identity.sessions import require_admin
from app.services.template_edit import detail, find_version, profiles_and_cases, snapshot


def fail(message, code='CONTENT_UNAVAILABLE'):
    raise ServiceError(409, code, message)


def actor(session, token, csrf, now):
    admin, stored = require_admin(session, token, now)
    check_csrf(csrf, stored.csrf_hash)
    return admin


def check_lock(row, expected):
    if row.lock_version != expected:
        fail('内容已变化，请重新加载', 'EDIT_CONFLICT')


def epoch(session, now):
    value = session.get(ContentEpoch, 1)
    value.value += 1
    value.updated_at = now
    return value.value


def audit(session, admin, action, target_type, target_id, request_id, reason, before, after, now):
    session.add(AdminOperationLog(admin_id=admin.id, action=action, target_type=target_type,
        target_id=target_id, request_id=str(request_id), reason=reason,
        before_summary=canonical(before), after_summary=canonical(after), created_at=now, updated_at=now))


def review_view(row):
    return ReviewView(id=row.id, validation_run_id=row.validation_run_id, content_hash=row.content_hash,
        decision=row.decision, comment=row.comment, sample_refs=json.loads(row.sample_refs),
        print_checked=bool(row.print_checked), reviewed_at=row.reviewed_at)


def reviews(session, version):
    return session.scalars(select(ContentReview).where(ContentReview.template_version_id == version.id)
        .order_by(ContentReview.reviewed_at.desc(), literal_column('content_review.rowid').desc()).limit(50)).all()


def context(session, version):
    fixed, _ = snapshot(session, version)
    dependencies = []
    seen = set()
    for target in fixed['targets']:
        knowledge = session.get(KnowledgeRevision, target['knowledge_revision_id'])
        objective = session.get(ObjectiveRevision, target['id'])
        for row, kind, description in ((knowledge, 'knowledge_revision', knowledge.definition + '\n边界：' + knowledge.boundary),
                                       (objective, 'objective_revision', objective.scope + '\n达成标准：' + '；'.join(json.loads(objective.success_criteria)))):
            if row.id not in seen:
                dependencies.append(DependencyView(id=row.id, kind=kind, name=row.name, description=description,
                    content_hash=row.content_hash, status=row.status, lock_version=row.lock_version))
                seen.add(row.id)
    template = session.get(QuestionTemplate, version.template_id)
    return ReleaseContext(template_id=template.id, template_lock_version=template.lock_version,
        template_status=template.status, current_published_version_id=template.current_published_version_id,
        dependencies=dependencies, reviews=[review_view(row) for row in reviews(session, version)])


def valid_run(session, version, identity, deployed):
    run = session.get(ValidationRun, str(identity))
    if run is None or run.template_version_id != version.id or run.content_hash != version.content_hash or run.status != 'passed':
        fail('必须使用当前版本、相同hash的有效通过报告')
    job = session.get(Job, run.job_id)
    if job.status != 'succeeded' or job.kind != 'template_validate' or not run.report:
        fail('验证任务尚未有效完成')
    fixed, generator = snapshot(session, version)
    payload = json.loads(job.payload)
    if (generator.deployment_status != 'available' or generator.artifact_hash != deployed['artifact_hash']
            or generator.key != deployed['key'] or generator.version != deployed['version']
            or generator.validator_version != deployed['validator_version']
            or json.loads(generator.param_schema) != deployed['param_schema']
            or json.loads(generator.output_schema) != deployed['output_schema']
            or fixed != payload['fixed'] or detail(session, version, deployed).config.model_dump(mode='json') != payload['config']):
        fail('配置或生成器已变化，原报告不能用于发布')
    report = ValidationReport.model_validate_json(run.report)
    if report.result != 'passed' or report.failure_count or not report.samples:
        fail('报告未通过或缺少审题样题')
    profiles, _ = profiles_and_cases(session, version)
    coverage = {c.difficulty: c.checked_count_options for c in report.coverage}
    if any(not coverage.get(p.difficulty) or json.loads(p.validated_count_options) != coverage[p.difficulty] for p in profiles):
        fail('有效题量与验证报告不一致')
    return run, report, fixed


def add_review(engine, identity, body, expected, *, token, csrf, now, request_id):
    deployed = definition()
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        version = find_version(session, identity)
        check_lock(version, expected)
        if version.status != 'draft' or version.content_hash != body.content_hash:
            fail('只能审查当前hash的草稿')
        run, report, _ = valid_run(session, version, body.validation_run_id, deployed)
        refs = {str(identity) for identity in body.sample_refs}
        known = {str(sample.id) for sample in report.samples}
        if not refs <= known or (body.decision == 'approved' and refs != known):
            raise ServiceError(422, 'INVALID_CONFIG', '通过前须审查报告全部样题；引用只能来自该报告')
        row = ContentReview(template_version_id=version.id, validation_run_id=run.id,
            content_hash=version.content_hash, decision=body.decision, reviewer_id=admin.id,
            comment=body.comment, sample_refs=canonical(sorted(refs)), print_checked=int(body.print_checked),
            reviewed_at=now, created_at=now, updated_at=now)
        session.add(row)
        session.flush()
        audit(session, admin, 'review', 'template_version', version.id, request_id, body.comment,
              {}, {'review_id': row.id, 'decision': row.decision}, now)
        return review_view(row)


def publish_revision(engine, kind, identity, body, expected, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        model = KnowledgeRevision if kind == 'knowledge_revision' else ObjectiveRevision
        row = session.get(model, str(identity))
        if row is None:
            raise ServiceError(404, 'NOT_FOUND', '修订不存在')
        check_lock(row, expected)
        if row.status != 'draft' or row.content_hash != body.content_hash:
            fail('修订状态或hash已变化')
        if kind == 'knowledge_revision':
            parent = session.get(KnowledgePoint, row.point_id)
        else:
            parent = session.get(TrainingObjective, row.objective_id)
            knowledge = session.get(KnowledgeRevision, row.knowledge_revision_id)
            if knowledge.status != 'published' or knowledge.point_id != parent.point_id:
                fail('请先发布同一知识点的关联修订')
            for code in json.loads(row.allowed_prerequisites):
                point = session.scalar(select(KnowledgePoint).where(KnowledgePoint.code == code))
                if point is None or point.status != 'active' or point.current_revision_id is None:
                    fail('先修知识点未发布')
        if parent.status == 'disabled':
            fail('主体已停用')
        row.status, row.updated_at = 'published', now
        row.lock_version += 1
        parent.current_revision_id, parent.status, parent.updated_at = row.id, 'active', now
        parent.lock_version += 1
        value = epoch(session, now)
        audit(session, admin, 'publish', kind, row.id, request_id, body.reason,
              {'status': 'draft'}, {'status': 'published', 'hash': row.content_hash, 'epoch': value}, now)


def release(engine, identity, body, expected, action, *, token, csrf, now, request_id):
    deployed = definition()
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        template = session.get(QuestionTemplate, str(identity))
        if template is None:
            raise ServiceError(404, 'NOT_FOUND', '模板不存在')
        check_lock(template, expected)
        previous = template.current_published_version_id
        run = review = version = None
        if action == 'disable':
            if template.status == 'disabled':
                fail('模板已停用')
            template.status = 'disabled'
        else:
            version = find_version(session, body.version_id)
            if version.template_id != template.id or version.status == 'retired':
                fail('版本不属于该模板或已经退役')
            if action == 'publish' and version.status != 'draft':
                fail('首次发布必须选择草稿版本')
            if action in ('enable', 'rollback') and version.status != 'published':
                fail('启用/回退只能选择已发布版本')
            if action == 'enable' and (template.status != 'disabled' or previous != version.id):
                fail('只能重新启用原发布版本')
            if action == 'rollback' and (previous == version.id or previous is None):
                fail('回退必须选择不同的历史发布版本')
            run, _, fixed = valid_run(session, version, body.validation_run_id, deployed)
            latest = next((item for item in reviews(session, version) if item.content_hash == version.content_hash), None)
            review = session.get(ContentReview, str(body.review_id))
            if (review is None or latest is None or review.id != latest.id or review.decision != 'approved'
                    or review.validation_run_id != run.id or not review.print_checked):
                fail('须使用同一报告绑定的最新人工通过记录')
            for target in fixed['targets']:
                objective = session.get(ObjectiveRevision, target['id'])
                knowledge = session.get(KnowledgeRevision, target['knowledge_revision_id'])
                point = session.get(KnowledgePoint, knowledge.point_id)
                owner = session.get(TrainingObjective, objective.objective_id)
                if (objective.status != 'published' or knowledge.status != 'published'
                        or point.status != 'active' or owner.status != 'active'
                        or owner.point_id != point.id):
                    fail('知识点和训练目标修订须先明确发布且主体启用')
            if action == 'publish':
                version.status = 'published'
                version.published_by, version.published_at, version.updated_at = admin.id, now, now
                version.lock_version += 1
            template.current_published_version_id, template.status = version.id, 'active'
        template.lock_version += 1
        template.updated_at = now
        value = epoch(session, now)
        row = ContentRelease(template_id=template.id, from_version_id=previous,
            to_version_id=version.id if version else None, action=action, operator_id=admin.id,
            reason=body.reason, validation_run_id=run.id if run else None, review_id=review.id if review else None,
            epoch=value, created_at=now, updated_at=now)
        session.add(row)
        session.flush()
        audit(session, admin, action, 'question_template', template.id, request_id, body.reason,
              {'version_id': previous}, {'version_id': template.current_published_version_id, 'status': template.status, 'epoch': value}, now)
        return ReleaseView.model_validate(row, from_attributes=True)


def clone_version(engine, identity, source_id, expected, *, token, csrf, now, request_id):
    deployed = definition()
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        template = session.get(QuestionTemplate, str(identity))
        if template is None:
            raise ServiceError(404, 'NOT_FOUND', '模板不存在')
        check_lock(template, expected)
        source = find_version(session, source_id)
        if source.template_id != template.id or source.status != 'published':
            fail('只能复制本模板已发布版本')
        if session.scalar(select(TemplateVersion.id).where(TemplateVersion.template_id == template.id, TemplateVersion.status == 'draft')):
            fail('已有草稿，请先继续编辑已有草稿')
        number = session.scalar(select(func.max(TemplateVersion.version_no)).where(TemplateVersion.template_id == template.id)) + 1
        version = TemplateVersion(template_id=template.id, version_no=number, generator_id=source.generator_id,
            question_type=source.question_type, render_mode=source.render_mode, content_schema_version=source.content_schema_version,
            stem_config=source.stem_config, answer_config=source.answer_config, explanation_config=source.explanation_config,
            diagram_config=source.diagram_config, content_hash=source.content_hash, created_by=admin.id,
            created_at=now, updated_at=now)
        session.add(version)
        session.flush()
        profiles, cases = profiles_and_cases(session, source)
        mapping = {}
        for profile in profiles:
            copied = TemplateProfile(template_version_id=version.id, difficulty=profile.difficulty,
                param_config=profile.param_config, constraint_config=profile.constraint_config,
                layout_config=profile.layout_config, semantic_dedupe_rule=profile.semantic_dedupe_rule,
                max_per_paper=profile.max_per_paper, profile_hash=profile.profile_hash, validated_count_options='[]',
                created_at=now, updated_at=now)
            session.add(copied)
            session.flush()
            mapping[profile.id] = copied.id
        for case in cases:
            session.add(TemplateTestCase(profile_id=mapping[case.profile_id], code=case.code, kind=case.kind,
                seed=case.seed, params=case.params, expected_properties=case.expected_properties, enabled=case.enabled,
                created_at=now, updated_at=now))
        for link in session.scalars(select(TemplateObjective).where(TemplateObjective.template_version_id == source.id)):
            session.add(TemplateObjective(template_version_id=version.id, objective_revision_id=link.objective_revision_id,
                role=link.role, created_at=now, updated_at=now))
        template.lock_version += 1
        template.updated_at = now
        audit(session, admin, 'clone', 'template_version', version.id, request_id, '从已发布版本复制草稿',
              {'source_version_id': source.id}, {'version_no': number}, now)
        session.flush()
        return detail(session, version, deployed)
