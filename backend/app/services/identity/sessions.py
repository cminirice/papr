from datetime import datetime, timedelta
from functools import lru_cache
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session
from app.auth.security import check_csrf, hash_password, new_token, token_hash, valid_token, verify_password, PASSWORD_HASHER
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.models.identity import AppUser, UserSession, AdminUser, AdminSession, RateLimitEvent
from app.schemas.identity import UserSessionView, UserSessionCreated, AdminSessionView, AdminSessionCreated
from app.services.identity.cooldown import active_job_id
from app.services.identity.limits import reserve_event

USER_TTL = timedelta(days=90)
RENEW_BEFORE = timedelta(days=7)
ADMIN_TTL = timedelta(hours=8)


def load_user(session: Session, token: str | None, now: datetime):
    if not valid_token(token):
        return None
    stored = session.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    if stored is None or stored.revoked_at or stored.expires_at <= now:
        return None
    user = session.get(AppUser, stored.user_id)
    if user is None or user.status != "active" or user.deleted_at:
        raise ServiceError(401, "SESSION_EXPIRED", "会话已失效")
    return user, stored


def require_user(session: Session, token: str | None, now: datetime):
    context = load_user(session, token, now)
    if context is None:
        raise ServiceError(401, "SESSION_EXPIRED", "会话已失效")
    return context


def require_admin(session: Session, token: str | None, now: datetime):
    stored = None
    if valid_token(token):
        stored = session.scalar(select(AdminSession).where(AdminSession.token_hash == token_hash(token)))
    if stored is None or stored.revoked_at or stored.expires_at <= now:
        raise ServiceError(401, "SESSION_EXPIRED", "管理员会话已失效")
    admin = session.get(AdminUser, stored.admin_id)
    if admin is None or admin.status != "active":
        raise ServiceError(401, "SESSION_EXPIRED", "管理员会话已失效")
    return admin, stored


def user_view(session: Session, user: AppUser, stored: UserSession, now: datetime) -> UserSessionView:
    active = active_job_id(session, user)
    return UserSessionView(user_id=user.id, expires_at=stored.expires_at, server_now=now,
        next_generation_at=user.next_generation_at, active_job_id=active,
        can_generate=active is None and (user.next_generation_at is None or now >= user.next_generation_at))


def touch_user(user: AppUser, stored: UserSession, now: datetime) -> bool:
    renewed = stored.expires_at - now < RENEW_BEFORE
    if renewed:
        stored.expires_at = now + USER_TTL
    user.last_seen_at = user.updated_at = now
    stored.last_seen_at = stored.updated_at = now
    return renewed


class IdentityService:
    def __init__(self, engine: Engine, identity_limit: int = 20):
        self.engine = engine
        self.identity_limit = identity_limit

    def bootstrap(self, token: str | None, subject: str, now: datetime):
        with write_transaction(self.engine) as session:
            reserve_event(session, "session_refresh", subject, now, limit=60, seconds=60)
            found = load_user(session, token, now)
            csrf = new_token()
            if found is None:
                reserve_event(session, "identity_create", subject, now, limit=self.identity_limit, seconds=3600)
                user = AppUser(first_seen_at=now, last_seen_at=now, created_at=now, updated_at=now)
                session.add(user)
                session.flush()
                token = new_token()
                stored = UserSession(user_id=user.id, token_hash=token_hash(token), csrf_hash=token_hash(csrf),
                    expires_at=now + USER_TTL, last_seen_at=now, created_at=now, updated_at=now)
                session.add(stored)
            else:
                user, stored = found
                touch_user(user, stored, now)
                stored.csrf_hash = token_hash(csrf)
            session.flush()
            data = UserSessionCreated(**user_view(session, user, stored, now).model_dump(), csrf_token=csrf)
        return data, token

    def read_user(self, token: str | None, now: datetime):
        with write_transaction(self.engine) as session:
            user, stored = require_user(session, token, now)
            renewed = touch_user(user, stored, now)
            data = user_view(session, user, stored, now)
        return data, renewed

    def rotate_user_csrf(self, token: str | None, subject: str, now: datetime):
        with write_transaction(self.engine) as session:
            user, stored = require_user(session, token, now)
            reserve_event(session, "session_refresh", subject, now, limit=60, seconds=60)
            csrf = new_token()
            stored.csrf_hash = token_hash(csrf)
            renewed = touch_user(user, stored, now)
            expires = stored.expires_at
        return csrf, renewed, expires

    def login(self, username: str, password: str, subject: str, now: datetime):
        # 先预占尝试名额，避免多个并发密码校验越过IP限制；高成本哈希在写锁外执行。
        with write_transaction(self.engine) as session:
            event = reserve_event(session, "admin_login", subject, now, limit=5, seconds=300)
            event_id = event.id
            admin = session.scalar(select(AdminUser).where(AdminUser.username == username))
            admin_id = admin.id if admin else None
            encoded = admin.password_hash if admin else None
            active = admin is not None and admin.status == "active"
        # 不存在用户也执行同等算法；dummy由调用方进程惰性生成并缓存。
        ok = verify_password(encoded or dummy_hash(), password)
        if not ok or not active:
            raise ServiceError(401, "LOGIN_FAILED", "用户名或密码错误")
        replacement = PASSWORD_HASHER.hash(password) if PASSWORD_HASHER.check_needs_rehash(encoded) else None
        with write_transaction(self.engine) as session:
            admin = session.get(AdminUser, admin_id)
            if admin is None or admin.status != "active" or admin.password_hash != encoded:
                raise ServiceError(401, "LOGIN_FAILED", "用户名或密码错误")
            session.delete(session.get(RateLimitEvent, event_id))
            if replacement:
                admin.password_hash = replacement
            admin.last_login_at = admin.updated_at = now
            token, csrf = new_token(), new_token()
            stored = AdminSession(admin_id=admin.id, token_hash=token_hash(token), csrf_hash=token_hash(csrf),
                expires_at=now + ADMIN_TTL, last_seen_at=now, created_at=now, updated_at=now)
            session.add(stored)
            data = AdminSessionCreated(admin_id=admin.id, expires_at=stored.expires_at, server_now=now, csrf_token=csrf)
        return data, token

    def read_admin(self, token: str | None, now: datetime):
        with write_transaction(self.engine) as session:
            admin, stored = require_admin(session, token, now)
            stored.last_seen_at = stored.updated_at = now
            return AdminSessionView(admin_id=admin.id, expires_at=stored.expires_at, server_now=now)

    def rotate_admin_csrf(self, token: str | None, subject: str, now: datetime):
        with write_transaction(self.engine) as session:
            _, stored = require_admin(session, token, now)
            reserve_event(session, "session_refresh", subject, now, limit=60, seconds=60)
            csrf = new_token()
            stored.csrf_hash = token_hash(csrf)
            stored.last_seen_at = stored.updated_at = now
        return csrf

    def logout(self, token: str | None, csrf: str | None, now: datetime):
        with write_transaction(self.engine) as session:
            _, stored = require_admin(session, token, now)
            check_csrf(csrf, stored.csrf_hash)
            stored.revoked_at = stored.updated_at = now


def initialize_admin(engine: Engine, username: str, password: str, now: datetime) -> str:
    import re
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", username):
        raise ValueError("管理员用户名仅允许1–64位字母、数字、下划线、点和短横线")
    encoded = hash_password(password)
    with write_transaction(engine) as session:
        if session.scalar(select(AdminUser.id).limit(1)):
            raise ValueError("管理员已存在；初始化不会覆盖账户或口令")
        admin = AdminUser(username=username, password_hash=encoded, created_at=now, updated_at=now)
        session.add(admin)
        session.flush()
        return admin.id


def disable_admin(session: Session, admin: AdminUser, now: datetime) -> None:
    """管理账户停用统一入口；与调用方操作记录处于同一事务。"""
    admin.status = "disabled"
    admin.updated_at = now
    admin.lock_version += 1
    session.execute(update(AdminSession).where(AdminSession.admin_id == admin.id, AdminSession.revoked_at.is_(None)).values(revoked_at=now, updated_at=now))


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    return hash_password(new_token())
