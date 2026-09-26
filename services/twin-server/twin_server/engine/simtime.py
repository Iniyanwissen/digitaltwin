"""Simulated time: float seconds since midnight of the run's start date (building timezone)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SECONDS_PER_DAY = 86_400.0


class SimTime:
    def __init__(self, start_date: date, tz: str) -> None:
        self.start_date = start_date
        self.tz = ZoneInfo(tz)
        self.base = datetime.combine(start_date, time(0), tzinfo=self.tz)

    def dt(self, t: float) -> datetime:
        return self.base + timedelta(seconds=t)

    def iso(self, t: float) -> str:
        return self.dt(t).isoformat(timespec="milliseconds")

    def day_date(self, day: int) -> date:
        return self.start_date + timedelta(days=day)

    @staticmethod
    def hour_of(t: float) -> float:
        return (t % SECONDS_PER_DAY) / 3600.0

    @staticmethod
    def day_start(t: float) -> float:
        return t - (t % SECONDS_PER_DAY)
