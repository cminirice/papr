"""Read-only administration: stable job paging and independent daily aggregates."""
from datetime import datetime, time, timedelta
import json
from sqlalchemy import and_, func, or_, select

from app.core.errors import ServiceError
from app.core.time import BEIJING, to_beijing
from app.models.content import QuestionTemplate, TemplateVersion
from app.models.jobs import Job
from app.models.events import UsageEvent
from app.schemas.events import UsageCounts
from app.models.papers import Paper, PaperQuestion, Question
from app.models.validation import ValidationRun
from app.schemas.admin_operations import (AdminJobSummary, AdminJobList, AdminJobDetail,
    AdminOverview, GenerationCounts, DailyGenerationCounts, QueueCounts)
from app.services.paper_jobs import cursor_for, parse_cursor
from app.services.validation_jobs import view as validation_view

ERRORS = {
    'WORKER_LOST': '执行服务中断，已达到自动尝试上限',
    'ENGINE_TIMEOUT': '模板验证超时',
    'VALIDATION_ENGINE_ERROR': '模板验证执行失败',
    'PREVIEW_ENGINE_ERROR': '草稿预览执行失败',
    'GENERATION_TIMEOUT': '出卷超时',
    'GENERATION_FAILED': '题目或PDF生成、保存未完成',
    'CONTENT_UNAVAILABLE': '模板或发布依据已变化，任务未提交',
}


def date_range(date_from, date_to, now):
    if date_from is None and date_to is None:
        date_to = to_beijing(now).date()
        date_from = date_to - timedelta(days=6)
    if date_from is None or date_to is None:
        raise ServiceError(422, 'INVALID_CONFIG', '请同时提供开始和结束日期')
    if not (1992 <= date_from.year <= date_to.year <= 9998) or not 0 <= (date_to - date_from).days < 93:
        raise ServiceError(422, 'INVALID_CONFIG', '日期须按先后顺序，单次查询不超过93天')
    start = datetime.combine(date_from, time.min, tzinfo=BEIJING)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=BEIJING)
    return date_from, date_to, start, end


def within(column, start, end):
    return and_(column >= start, column < end)


def job_query():
    # Each joined relation is at most one row per job; never join questions/assets here.
    version_id = func.coalesce(ValidationRun.template_version_id,
                              func.json_extract(Job.payload, '$.template_version_id'))
    return (select(Job, Paper, ValidationRun, TemplateVersion, QuestionTemplate).select_from(Job)
        .outerjoin(Paper, Paper.job_id == Job.id)
        .outerjoin(ValidationRun, ValidationRun.job_id == Job.id)
        .outerjoin(TemplateVersion, TemplateVersion.id == version_id)
        .outerjoin(QuestionTemplate, QuestionTemplate.id == TemplateVersion.template_id))


def summary(row):
    job, paper, run, version, template = row
    payload = json.loads(job.payload) if job.kind in ('paper_generate', 'template_preview') else {}
    request = payload.get('request', {})
    counts = request.get('question_type_counts', {})
    # Raw payload/error text may contain internal paths. Only export explicit public fields.
    code = job.error_code if job.error_code in ERRORS else ('TASK_FAILED' if job.error_code else None)
    return AdminJobSummary(id=job.id, kind=job.kind, status=job.status, phase=job.phase,
        attempt=job.attempt, max_attempts=job.max_attempts,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
        error_code=code, error_message=ERRORS.get(code, '任务未完成，请核对验证报告') if code else None,
        template_id=template.id if template else None, template_name=template.name if template else None,
        template_version_id=version.id if version else None, version_no=version.version_no if version else None,
        validation_run_id=run.id if run else None, validation_status=run.status if run else None,
        paper_id=paper.id if paper else None, paper_status=paper.status if paper else None,
        difficulty=paper.difficulty if paper else request.get('difficulty'),
        total_count=paper.total_count if paper else sum(counts.values()) if counts else request.get('count'),
        theme_name=payload.get('catalog_snapshot', {}).get('theme_name'))


def listing(session, period, kind=None, status=None, cursor=None, limit=20):
    date_from, date_to, start, end = period
    query = job_query().where(within(Job.created_at, start, end))
    if kind:
        query = query.where(Job.kind == kind)
    if status:
        query = query.where(Job.status == status)
    if cursor:
        created, identity = parse_cursor(cursor)
        query = query.where(or_(Job.created_at < created, and_(Job.created_at == created, Job.id < identity)))
    rows = session.execute(query.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return AdminJobList(date_from=date_from, date_to=date_to, items=[summary(row) for row in rows],
        has_more=more, next_cursor=cursor_for(rows[-1][0]) if more else None)


def detail(session, identity):
    row = session.execute(job_query().where(Job.id == str(identity))).one_or_none()
    if row is None:
        raise ServiceError(404, 'NOT_FOUND', '任务不存在')
    job, paper, run, *_ = row
    questions = session.scalars(select(Question.content_snapshot).join(PaperQuestion,
        PaperQuestion.question_id == Question.id).where(PaperQuestion.paper_id == paper.id)
        .order_by(PaperQuestion.position)).all() if paper else []
    if job.kind == 'template_preview' and job.status == 'succeeded' and job.result:
        questions = [json.dumps(q) for q in json.loads(job.result)['questions']]
    job_summary = summary(row)
    validation = validation_view(session, run) if run else None
    if validation:
        validation.error_code = job_summary.error_code
    return AdminJobDetail(job=job_summary, questions=[json.loads(q) for q in questions], validation=validation)


def overview(session, period, now):
    date_from, date_to, start, end = period
    days = {str(date_from + timedelta(days=n)): DailyGenerationCounts(date=date_from + timedelta(days=n))
            for n in range((date_to - date_from).days + 1)}
    submitted_day = func.substr(Job.created_at, 1, 10)
    submitted = session.execute(select(submitted_day, func.count(), func.count(func.distinct(Job.owner_user_id)))
        .where(Job.kind == 'paper_generate', within(Job.created_at, start, end)).group_by(submitted_day)).all()
    for day, count, active in submitted:
        days[day].submitted, days[day].active_subjects = count, active
    # Count a committed paper once, including later withdrawals; no fan-out from PDF/question joins.
    success_day = func.substr(Paper.generated_at, 1, 10)
    for day, count in session.execute(select(success_day, func.count()).select_from(Paper)
            .join(Job, Job.id == Paper.job_id).where(Job.status == 'succeeded',
                within(Paper.generated_at, start, end)).group_by(success_day)):
        days[day].succeeded = count
    finished_day = func.substr(Job.finished_at, 1, 10)
    for day, status, count in session.execute(select(finished_day, Job.status, func.count())
            .where(Job.kind == 'paper_generate', Job.status.in_(['failed', 'cancelled']),
                within(Job.finished_at, start, end)).group_by(finished_day, Job.status)):
        setattr(days[day], status, count)
    active_subjects = session.scalar(select(func.count(func.distinct(Job.owner_user_id)))
        .where(Job.kind == 'paper_generate', within(Job.created_at, start, end)))
    totals = GenerationCounts(**{name: sum(getattr(day, name) for day in days.values())
        for name in ('submitted', 'succeeded', 'failed', 'cancelled')}, active_subjects=active_subjects)
    queues = {kind: QueueCounts() for kind in ('paper_generate', 'template_validate')}
    for kind, status, count in session.execute(select(Job.kind, Job.status, func.count())
            .where(Job.kind.in_(queues), Job.status.in_(['queued', 'running'])).group_by(Job.kind, Job.status)):
        setattr(queues[kind], status, count)
    usage=UsageCounts()
    for kind,count in session.execute(select(UsageEvent.event_type,func.count()).where(within(UsageEvent.received_at,start,end)).group_by(UsageEvent.event_type)):
        setattr(usage,kind,count)
    return AdminOverview(usage=usage,date_from=date_from, date_to=date_to, as_of=now, totals=totals,
        daily=list(days.values()), generation_queue=queues['paper_generate'], validation_queue=queues['template_validate'])
