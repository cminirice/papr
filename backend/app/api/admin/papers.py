from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.auth.http import clock
from app.api.admin.releases import credentials, expected
from app.api.admin.operations import CalendarDate
from app.schemas.common import Envelope
from app.schemas.paper_admin import AdminPaperList, AdminPaperDetail, NoticeCreate
from app.schemas.releases import DisableRequest
from app.services import paper_admin, admin_operations
router=APIRouter(prefix='/admin/api/v1',tags=['admin-papers'],dependencies=[Depends(current_admin)])


@router.get('/papers',response_model=Envelope[AdminPaperList])
def listing(request:Request,date_from:CalendarDate|None=None,date_to:CalendarDate|None=None,
            status:Literal['active','withdrawn']|None=None,owner_user_id:UUID|None=None,template_version_id:UUID|None=None,
            cursor:str|None=Query(default=None,max_length=256),limit:int=Query(default=20,ge=1,le=100)):
    period=admin_operations.date_range(date_from,date_to,clock(request))
    bounds=period[2:]
    with Session(request.app.state.engine) as session:
        data=paper_admin.listing(session,bounds,status,owner_user_id,template_version_id,cursor,limit)
    return Envelope(data=data,request_id=request.state.request_id)


@router.get('/papers/{identity}',response_model=Envelope[AdminPaperDetail])
def detail(identity:UUID,request:Request):
    with Session(request.app.state.engine) as session:data=paper_admin.detail(session,identity)
    return Envelope(data=data,request_id=request.state.request_id)


@router.post('/papers/{identity}/notices',response_model=Envelope[AdminPaperDetail])
def notice(identity:UUID,body:NoticeCreate,request:Request,idempotency_key:UUID=Header(),if_match:str|None=Header(default=None)):
    data=paper_admin.add_notice(request.app.state.engine,identity,body,idempotency_key,expected(if_match),**credentials(request))
    return Envelope(data=data,request_id=request.state.request_id)


@router.post('/jobs/{identity}/cancel',status_code=204)
def cancel(identity:UUID,body:DisableRequest,request:Request):
    paper_admin.cancel(request.app.state.engine,identity,body.reason,**credentials(request))
    return Response(status_code=204)
