from pydantic import ValidationError
from sqlalchemy import select
from app.auth.security import check_csrf
from app.core.database import write_transaction
from app.models.events import UsageEvent
from app.models.papers import Paper
from app.schemas.events import EventInput, EventResult, EventRejection
from app.services.identity.sessions import require_user
from app.services.content_seed import canonical, digest


def accept(engine, body, *, token, csrf, now):
    result=EventResult(accepted_ids=[],duplicate_ids=[],rejected=[])
    with write_transaction(engine) as session:
        user,stored=require_user(session,token,now);check_csrf(csrf,stored.csrf_hash)
        for raw in body.events:
            try:event=EventInput.model_validate(raw)
            except ValidationError:
                identity=raw.get('event_id')
                result.rejected.append(EventRejection(event_id=identity[:100] if isinstance(identity,str) else None,code='INVALID_CONFIG'))
                continue
            identity=str(event.event_id)
            fingerprint=digest(event.model_dump(mode='json'))
            existing=session.scalar(select(UsageEvent).where(UsageEvent.owner_user_id==user.id,UsageEvent.event_id==identity))
            if existing:
                if existing.request_hash==fingerprint:result.duplicate_ids.append(event.event_id)
                else:result.rejected.append(EventRejection(event_id=identity,code='EVENT_CONFLICT'))
                continue
            paper=session.get(Paper,str(event.paper_id))
            if paper is None or paper.owner_user_id!=user.id or paper.deleted_at is not None or (event.type=='print_intent' and paper.status!='active'):
                result.rejected.append(EventRejection(event_id=identity,code='NOT_FOUND'));continue
            session.add(UsageEvent(event_id=identity,owner_user_id=user.id,paper_id=paper.id,event_type=event.type,
                payload=canonical(event.payload.model_dump()),request_hash=fingerprint,occurred_at=event.occurred_at,
                received_at=now,created_at=now,updated_at=now))
            session.flush()
            result.accepted_ids.append(event.event_id)
    return result
