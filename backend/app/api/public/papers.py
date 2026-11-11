import base64
import json
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from app.auth.dependencies import Principal, current_user
from app.core.errors import ServiceError
from app.core.time import serialize_time
from app.models.jobs import Job
from app.models.papers import Paper, PaperQuestion, Question, FileAsset, PaperNotice
from app.schemas.common import Envelope
from app.schemas.papers import PaperFile, PaperSummary, PaperDetail, PaperList, PaperSelection, NoticeView
from app.schemas.paper_jobs import PaperPlan
from app.services.content_seed import canonical
from app.services.paper_jobs import parse_cursor
from app.services.pdf_storage import PdfTarget, SavedPdf, read_verified, PdfStorageError

router = APIRouter(prefix='/api/v1', tags=['papers'])


def accessible(owner, *, downloadable=False):
    query = select(Paper).join(Job, Job.id == Paper.job_id).where(Paper.owner_user_id == owner,
        Paper.deleted_at.is_(None), Job.status == 'succeeded')
    return query.where(Paper.status == 'active') if downloadable else query


def summary(session, paper):
    files = session.scalars(select(FileAsset).where(FileAsset.paper_id == paper.id,
        FileAsset.owner_user_id == paper.owner_user_id, FileAsset.job_id == paper.job_id,
        FileAsset.status == 'ready').order_by(FileAsset.kind)).all()
    catalog = json.loads(paper.catalog_snapshot)
    notices = session.scalars(select(PaperNotice).where(PaperNotice.paper_id == paper.id).order_by(PaperNotice.created_at, PaperNotice.id)).all()
    return PaperSummary(status=paper.status, notices=[NoticeView(id=n.id, question_id=n.question_id, severity=n.severity, action=n.action, message=n.message, created_at=n.created_at) for n in notices], id=paper.id, title=paper.title, difficulty=paper.difficulty,
        catalog_name=catalog['catalog_name'], theme_name=catalog['theme_name'],
        question_type_counts={'choice': paper.choice_count, 'fill': paper.fill_count, 'answer': paper.answer_count},
        total_count=paper.total_count, generated_at=paper.generated_at,
        files=[PaperFile(id=f.id, kind=f.kind, pages=f.pages, byte_size=f.byte_size) for f in files] if paper.status == 'active' else [])


@router.get('/papers', response_model=Envelope[PaperList])
def listing(request: Request, principal: Principal = Depends(current_user),
            limit: int = Query(default=20, ge=1, le=100), cursor: str | None = Query(default=None, max_length=256)):
    with Session(request.app.state.engine) as session:
        query = accessible(principal.owner_id)
        if cursor:
            date, identity = parse_cursor(cursor)
            query = query.where(or_(Paper.generated_at < date, and_(Paper.generated_at == date, Paper.id < identity)))
        rows = session.scalars(query.order_by(Paper.generated_at.desc(), Paper.id.desc()).limit(limit + 1)).all()
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = base64.urlsafe_b64encode(canonical([serialize_time(rows[-1].generated_at), rows[-1].id]).encode()).decode().rstrip('=') if more else None
        data = PaperList(items=[summary(session, p) for p in rows], next_cursor=next_cursor, has_more=more)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/papers/{identity}', response_model=Envelope[PaperDetail])
def detail(identity: UUID, request: Request, principal: Principal = Depends(current_user)):
    with Session(request.app.state.engine) as session:
        paper = session.scalar(accessible(principal.owner_id).where(Paper.id == str(identity)))
        if paper is None:
            raise ServiceError(404, 'NOT_FOUND', '试卷不存在')
        questions = session.scalars(select(Question).join(PaperQuestion, Question.id == PaperQuestion.question_id)
                                   .where(PaperQuestion.paper_id == paper.id).order_by(PaperQuestion.position)).all()
        plan = PaperPlan.model_validate_json(paper.config_snapshot)
        selection = PaperSelection(catalog_id=plan.catalog_snapshot['catalog_id'],
            theme_id=plan.request.theme_id, knowledge_point_ids=plan.request.knowledge_point_ids,
            difficulty=plan.request.difficulty, question_type_counts=plan.request.question_type_counts)
        data = PaperDetail(**summary(session, paper).model_dump(), questions=[json.loads(q.content_snapshot) for q in questions],
                           selection=selection)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/files/{identity}', response_class=Response, responses={200: {'content': {'application/pdf': {}}}})
def download(identity: UUID, request: Request, response: Response, principal: Principal = Depends(current_user),
             disposition: str = Query(default='attachment', pattern='^(attachment|inline)$')):
    with Session(request.app.state.engine) as session:
        asset = session.scalar(select(FileAsset).where(FileAsset.id == str(identity),
            FileAsset.owner_user_id == principal.owner_id, FileAsset.status == 'ready'))
        paper = session.scalar(accessible(principal.owner_id, downloadable=True).where(Paper.id == asset.paper_id)) if asset else None
        if paper is None or asset.job_id != paper.job_id:
            raise ServiceError(404, 'NOT_FOUND', '文件不存在')
        try:
            target = PdfTarget(UUID(asset.id), asset.created_at)
            if target.storage_key != asset.storage_key:
                raise ValueError('STORAGE_KEY_MISMATCH')
            saved = SavedPdf(target, asset.byte_size, asset.sha256, asset.pages, json.loads(asset.metadata_json)['parser'])
        except (ValueError, KeyError, TypeError):
            raise ServiceError(503, 'FILE_UNAVAILABLE', '文件暂不可用') from None
        filename = f'papr-{paper.id}-{asset.kind}.pdf'
    try:
        content = read_verified(request.app.state.settings.generated_root, saved)
    except PdfStorageError:
        raise ServiceError(503, 'FILE_UNAVAILABLE', '文件暂不可用') from None
    result = Response(content, media_type='application/pdf', headers={
        'Content-Disposition': f'{disposition}; filename="{filename}"', 'X-Content-Type-Options': 'nosniff'})

    for cookie in response.headers.getlist('set-cookie'):
        result.headers.append('set-cookie', cookie)
    return result
