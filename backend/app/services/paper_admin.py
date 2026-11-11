import base64
import json
from sqlalchemy import select, and_, or_, func
from app.api.public.papers import summary
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.core.time import serialize_time
from app.models.papers import Paper, PaperNotice, Question, PaperQuestion
from app.models.content import TemplateVersion, QuestionTemplate
from app.models.jobs import Job
from app.models.validation import ValidationRun
from app.schemas.paper_admin import AdminPaperSummary, AdminPaperDetail, AdminPaperList, SourceVersion
from app.services.paper_jobs import parse_cursor
from app.services.content_seed import canonical, digest
from app.services.releases import actor, audit


def paper_row(session, identity):
    row=session.get(Paper,str(identity))
    if row is None or row.deleted_at is not None:
        raise ServiceError(404,'NOT_FOUND','试卷不存在')
    return row


def admin_summary(session,paper):
    return AdminPaperSummary(**summary(session,paper).model_dump(),owner_user_id=paper.owner_user_id,job_id=paper.job_id)


def detail(session,identity):
    paper=paper_row(session,identity)
    questions=session.scalars(select(Question).join(PaperQuestion,PaperQuestion.question_id==Question.id).where(PaperQuestion.paper_id==paper.id).order_by(PaperQuestion.position)).all()
    sources=[]
    for identity in sorted({q.template_version_id for q in questions}):
        version=session.get(TemplateVersion,identity);template=session.get(QuestionTemplate,version.template_id)
        sources.append(SourceVersion(template_id=template.id,version_id=version.id,template_name=template.name))
    result=admin_summary(session,paper)
    return AdminPaperDetail(**result.model_dump(),lock_version=1+len(result.notices),questions=[json.loads(q.content_snapshot) for q in questions],sources=sources)


def listing(session,period,status,owner,version,cursor,limit):
    start,end=period
    query=select(Paper).where(Paper.deleted_at.is_(None),Paper.generated_at>=start,Paper.generated_at<end)
    if status:query=query.where(Paper.status==status)
    if owner:query=query.where(Paper.owner_user_id==str(owner))
    if version:
        query=query.where(Paper.id.in_(select(PaperQuestion.paper_id).join(Question,Question.id==PaperQuestion.question_id).where(Question.template_version_id==str(version))))
    if cursor:
        when,identity=parse_cursor(cursor)
        query=query.where(or_(Paper.generated_at<when,and_(Paper.generated_at==when,Paper.id<identity)))
    rows=list(session.scalars(query.order_by(Paper.generated_at.desc(),Paper.id.desc()).limit(limit+1)))
    more=len(rows)>limit;rows=rows[:limit]
    next_cursor=base64.urlsafe_b64encode(canonical([serialize_time(rows[-1].generated_at),rows[-1].id]).encode()).decode().rstrip('=') if more else None
    return AdminPaperList(items=[admin_summary(session,p) for p in rows],next_cursor=next_cursor,has_more=more)


def add_notice(engine,identity,body,key,expected,*,token,csrf,now,request_id):
    request_hash=digest({'paper_id':str(identity),**body.model_dump(mode='json')})
    if not body.message.strip():raise ServiceError(422,'INVALID_CONFIG','说明不能为空')
    with write_transaction(engine) as session:
        admin=actor(session,token,csrf,now);paper=paper_row(session,identity)
        existing=session.get(PaperNotice,str(key))
        if existing:
            if existing.request_hash != request_hash:
                raise ServiceError(409,'IDEMPOTENCY_CONFLICT','同一请求编号不能用于不同说明')
            return detail(session,paper.id)
        current=1+session.scalar(select(func.count()).select_from(PaperNotice).where(PaperNotice.paper_id==paper.id))
        if expected!=current:raise ServiceError(409,'EDIT_CONFLICT','试卷说明已变化，请重新加载')
        if body.question_id and not session.scalar(select(PaperQuestion.id).where(PaperQuestion.paper_id==paper.id,PaperQuestion.question_id==str(body.question_id))):
            raise ServiceError(422,'INVALID_CONFIG','题目不属于该试卷')
        before=paper.status
        session.add(PaperNotice(id=str(key),request_hash=request_hash,paper_id=paper.id,question_id=str(body.question_id) if body.question_id else None,
            severity=body.severity,action=body.action,message=body.message,created_by=admin.id,created_at=now,updated_at=now))
        if body.action=='withdraw':paper.status='withdrawn';paper.updated_at=now
        audit(session,admin,body.action,'paper',paper.id,request_id,body.reason,{'status':before},
              {'status':paper.status,'notice_id':str(key),'question_id':str(body.question_id) if body.question_id else None},now)
        session.flush();return detail(session,paper.id)


def cancel(engine,identity,reason,*,token,csrf,now,request_id):
    with write_transaction(engine) as session:
        admin=actor(session,token,csrf,now);job=session.get(Job,str(identity))
        if not job:raise ServiceError(404,'NOT_FOUND','任务不存在')
        if job.status=='cancelled':return
        if job.status!='queued':raise ServiceError(409,'JOB_NOT_CANCELLABLE','仅能取消尚未开始的排队任务')
        job.status='cancelled';job.phase='done';job.finished_at=job.updated_at=now
        job.lease_token=job.lease_until=None
        if job.kind=='template_validate':
            run=session.scalar(select(ValidationRun).where(ValidationRun.job_id==job.id))
            if run:run.status='failed';run.finished_at=run.updated_at=now
        audit(session,admin,'cancel','job',job.id,request_id,reason,{'status':'queued'},{'status':'cancelled','kind':job.kind},now)
