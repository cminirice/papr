from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.auth.http import clock
from app.api.admin.operations import CalendarDate
from app.schemas.common import Envelope
from app.schemas.audit import OperationList
from app.services.admin_operations import date_range
from app.services import audit_query
router=APIRouter(prefix='/admin/api/v1',tags=['admin-audit'],dependencies=[Depends(current_admin)])


@router.get('/operations',response_model=Envelope[OperationList])
def listing(request:Request,date_from:CalendarDate|None=None,date_to:CalendarDate|None=None,admin_id:UUID|None=None,
            target_type:str|None=Query(default=None,max_length=64),target_id:str|None=Query(default=None,max_length=100),
            action:str|None=Query(default=None,max_length=64),cursor:str|None=Query(default=None,max_length=256),
            limit:int=Query(default=20,ge=1,le=100)):
    period=date_range(date_from,date_to,clock(request))
    with Session(request.app.state.engine) as session:
        data=audit_query.listing(session,period,admin_id,target_type,target_id,action,cursor,limit)
    return Envelope(data=data,request_id=request.state.request_id)
