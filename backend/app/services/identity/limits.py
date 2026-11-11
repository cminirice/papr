from datetime import datetime, timedelta
from math import ceil
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.errors import ServiceError
from app.models.identity import RateLimitEvent


def reserve_event(session: Session, action: str, subject_hash: str, now: datetime, *, limit: int, seconds: int) -> RateLimitEvent:
    # 仅清理24小时前的技术限流事件，不涉及正式身份或历史。
    session.execute(delete(RateLimitEvent).where(RateLimitEvent.created_at <= now - timedelta(hours=24)))
    events = list(session.scalars(select(RateLimitEvent.created_at).where(
        RateLimitEvent.action == action,
        RateLimitEvent.subject_hash == subject_hash,
        RateLimitEvent.created_at > now - timedelta(seconds=seconds),
    ).order_by(RateLimitEvent.created_at).limit(limit)))
    if len(events) >= limit:
        retry = max(1, ceil((events[0] + timedelta(seconds=seconds) - now).total_seconds()))
        raise ServiceError(429, "RATE_LIMITED", "请求过于频繁，请稍后重试", headers={"Retry-After": str(retry)})
    event = RateLimitEvent(action=action, subject_hash=subject_hash, created_at=now, updated_at=now)
    session.add(event)
    session.flush()
    return event
