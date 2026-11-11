from fastapi import APIRouter, Depends, Request
from app.auth.dependencies import current_user
from app.auth.http import USER_COOKIE, clock
from app.schemas.common import Envelope
from app.schemas.events import EventBatch, EventResult
from app.services.events import accept
router=APIRouter(prefix='/api/v1',tags=['events'],dependencies=[Depends(current_user)])


@router.post('/events',response_model=Envelope[EventResult])
def events(body:EventBatch,request:Request):
    data=accept(request.app.state.engine,body,token=request.cookies.get(USER_COOKIE),csrf=request.headers.get('X-CSRF-Token'),now=clock(request))
    return Envelope(data=data,request_id=request.state.request_id)
