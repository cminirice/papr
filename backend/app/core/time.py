"""业务时间统一入口；SQLite 和 JSON 都保留显式北京时间偏移。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def to_beijing(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    result = value.astimezone(BEIJING)
    if result.utcoffset() != timedelta(hours=8):
        raise ValueError("业务时间不支持历史夏令时日期")
    return result


def serialize_time(value: datetime) -> str:
    return to_beijing(value).isoformat(timespec="microseconds")


def parse_stored_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if serialize_time(parsed) != value:
        raise ValueError("数据库时间必须为固定微秒精度及 +08:00 格式")
    return parsed.astimezone(BEIJING)
