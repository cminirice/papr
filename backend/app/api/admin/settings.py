from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.api.admin.releases import credentials, expected
from app.schemas.common import Envelope
from app.schemas.settings import SettingKey, SettingEdit, SettingView, SettingList
from app.services import settings
router = APIRouter(prefix='/admin/api/v1/settings', tags=['admin-settings'], dependencies=[Depends(current_admin)])


@router.get('', response_model=Envelope[SettingList])
def listing(request: Request):
    with Session(request.app.state.engine) as session:
        data = settings.listing(session)
    return Envelope(data=data, request_id=request.state.request_id)


@router.patch('/{key}', response_model=Envelope[SettingView])
def save(key: SettingKey, body: SettingEdit, request: Request, if_match: str | None = Header(default=None)):
    data = settings.save(request.app.state.engine, key, body, expected(if_match), **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)
