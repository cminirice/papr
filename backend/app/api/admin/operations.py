from datetime import date
import re
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BeforeValidator
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.auth.http import clock
from app.schemas.admin_operations import AdminJobDetail, AdminJobList, AdminOverview, JobKind, JobStatus
from app.schemas.common import Envelope
from app.services import admin_operations

router = APIRouter(prefix='/admin/api/v1', tags=['admin-operations'], dependencies=[Depends(current_admin)])


def calendar_date(value):
    if not isinstance(value, str) or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None:
        raise ValueError('日期必须为YYYY-MM-DD')
    return value


CalendarDate = Annotated[date, BeforeValidator(calendar_date)]


@router.get('/overview', response_model=Envelope[AdminOverview])
def overview(request: Request, date_from: CalendarDate | None = None, date_to: CalendarDate | None = None):
    now = clock(request)
    period = admin_operations.date_range(date_from, date_to, now)
    with Session(request.app.state.engine) as session:
        data = admin_operations.overview(session, period, now)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/jobs', response_model=Envelope[AdminJobList])
def jobs(request: Request, date_from: CalendarDate | None = None, date_to: CalendarDate | None = None,
         kind: JobKind | None = None, status: JobStatus | None = None,
         cursor: str | None = Query(default=None, max_length=256), limit: int = Query(default=20, ge=1, le=100)):
    period = admin_operations.date_range(date_from, date_to, clock(request))
    with Session(request.app.state.engine) as session:
        data = admin_operations.listing(session, period, kind, status, cursor, limit)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/jobs/{identity}', response_model=Envelope[AdminJobDetail])
def job(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = admin_operations.detail(session, identity)
    return Envelope(data=data, request_id=request.state.request_id)
