from datetime import datetime, timedelta
from math import ceil
from sqlalchemy import select, inspect
from sqlalchemy.orm import Session
from app.core.errors import ServiceError
from app.core.time import to_beijing
from app.models.identity import AppUser
from app.models.jobs import Job


def active_job_id(session: Session, user: AppUser) -> str | None:
    active = session.scalar(select(Job.id).where(Job.owner_user_id == user.id, Job.kind == "paper_generate", Job.status.in_(["queued", "running"])))
    if active:return active
    if inspect(session.connection()).has_table('v2_task'):
        from app.v2.models import Task
        return session.scalar(select(Task.id).where(Task.user_id==user.id,Task.status.in_(['queued','running'])))
    return None


def check_generation_admission(session: Session, user: AppUser, now: datetime) -> None:
    """T4在BEGIN IMMEDIATE内完成幂等检查后调用；不提交、不设置冷却。"""
    now = to_beijing(now)
    if user.status != "active" or user.deleted_at is not None:
        raise ServiceError(401, "SESSION_EXPIRED", "会话已失效")
    active = active_job_id(session, user)
    if active:
        raise ServiceError(409, "ACTIVE_JOB_EXISTS", "已有练习正在生成", details={"active_job_id": active})
    if user.next_generation_at and now < user.next_generation_at:
        retry = ceil((user.next_generation_at - now).total_seconds())
        raise ServiceError(429, "GENERATION_COOLDOWN", "请等待本次冷却结束", headers={"Retry-After": str(retry)})


def record_generation_success(session: Session, user: AppUser, now: datetime) -> None:
    """仅供T4完整成功事务调用；文件/租约/幂等由调用方验证，不自行提交。"""
    now = to_beijing(now)
    user.last_generation_succeeded_at = now
    user.next_generation_at = now + timedelta(seconds=600)
    user.updated_at = now
    session.add(user)
