"""Read-only, stable audit pagination with credential fields excluded."""
import json
from sqlalchemy import select, and_, or_
from app.models.releases import AdminOperationLog
from app.schemas.audit import OperationView, OperationList
from app.services.paper_jobs import parse_cursor, cursor_for


def safe_summary(raw):
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key,item in value.items()
                    if not any(word in key.lower() for word in ('password','secret','cookie','csrf','token','credential'))}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean(json.loads(raw)) if raw else None


def listing(session, period, admin_id=None, target_type=None, target_id=None, action=None, cursor=None, limit=20):
    date_from,date_to,start,end=period
    query=select(AdminOperationLog).where(AdminOperationLog.created_at>=start,AdminOperationLog.created_at<end)
    for field,value in ((AdminOperationLog.admin_id,admin_id),(AdminOperationLog.target_type,target_type),
                        (AdminOperationLog.target_id,target_id),(AdminOperationLog.action,action)):
        if value is not None:query=query.where(field==str(value))
    if cursor:
        created,identity=parse_cursor(cursor)
        query=query.where(or_(AdminOperationLog.created_at<created,and_(AdminOperationLog.created_at==created,AdminOperationLog.id<identity)))
    rows=session.scalars(query.order_by(AdminOperationLog.created_at.desc(),AdminOperationLog.id.desc()).limit(limit+1)).all()
    more=len(rows)>limit;rows=rows[:limit]
    return OperationList(date_from=date_from,date_to=date_to,has_more=more,next_cursor=cursor_for(rows[-1]) if more else None,
        items=[OperationView(id=r.id,admin_id=r.admin_id,action=r.action,target_type=r.target_type,target_id=r.target_id,
            request_id=r.request_id,before_summary=safe_summary(r.before_summary),after_summary=safe_summary(r.after_summary),
            reason=r.reason,created_at=r.created_at) for r in rows])
