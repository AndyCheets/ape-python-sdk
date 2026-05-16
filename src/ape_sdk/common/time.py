from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_timezone(name: str) -> ZoneInfo:
    return ZoneInfo(name)

