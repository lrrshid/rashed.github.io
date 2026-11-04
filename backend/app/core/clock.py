"""Injectable clock. Services never call datetime.now() directly so tests and the demo seeder can control time."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class Clock:
    def now(self) -> datetime:
        """Current instant as an aware UTC datetime."""
        raise NotImplementedError

    def today(self, zone: ZoneInfo) -> date:
        """Current calendar date in the given (company) time zone."""
        return self.now().astimezone(zone).date()


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock(Clock):
    """A clock that only moves when told to. Used by tests and by the demo seeder."""

    def __init__(self, instant: datetime):
        self._instant = to_utc(instant)

    def now(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        self._instant = to_utc(instant)

    def advance(self, **kwargs) -> None:
        self._instant = self._instant + timedelta(**kwargs)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("naive datetimes are not allowed; attach a time zone")
    return value.astimezone(timezone.utc)


def local_date(instant: datetime, zone: ZoneInfo) -> date:
    return to_utc(instant).astimezone(zone).date()


def iso_utc(value: datetime | None) -> str | None:
    """ISO 8601 UTC with a trailing Z and millisecond precision, e.g. 2026-10-08T05:00:00.000Z."""
    if value is None:
        return None
    return to_utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")
