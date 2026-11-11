import hashlib
import hmac
import ipaddress
import re
import secrets
from pathlib import Path

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from app.core.errors import ServiceError

PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def valid_token(value: str | None) -> bool:
    return isinstance(value, str) and TOKEN_PATTERN.fullmatch(value) is not None


def check_csrf(value: str | None, expected_hash: str) -> None:
    if not valid_token(value) or not hmac.compare_digest(token_hash(value), expected_hash):
        raise ServiceError(403, "CSRF_INVALID", "请求校验已失效，请刷新后重试")


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError("管理员口令长度须为12–128个字符")
    return PASSWORD_HASHER.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def initialize_rate_key(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # O_EXCL防止重复运行或并发初始化时覆盖既有密钥。
        import os
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        load_rate_key(path)
        return False
    with os.fdopen(fd, "wb") as stream:
        stream.write(secrets.token_bytes(32))
        stream.flush()
        os.fsync(stream.fileno())
    return True


def load_rate_key(path: Path) -> bytes:
    try:
        value = path.read_bytes()
    except OSError:
        raise ServiceError(503, "SERVICE_NOT_READY", "身份服务尚未初始化") from None
    if len(value) != 32:
        raise ServiceError(503, "SERVICE_NOT_READY", "身份服务配置不可用")
    return value


def ip_subject(host: str, key: bytes) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ServiceError(503, "SERVICE_NOT_READY", "无法识别请求来源") from None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return hmac.new(key, str(address).encode(), hashlib.sha256).hexdigest()
