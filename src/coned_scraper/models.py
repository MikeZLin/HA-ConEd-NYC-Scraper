from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class SourceName(StrEnum):
    WEBSITE_API = "website_api"
    OPOWER = "opower"


class ReadingQuality(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("interval timestamps must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class IntervalReading:
    account_id: str
    start_time: datetime
    end_time: datetime
    energy_kwh: float
    average_power_w: float
    source: SourceName
    source_resolution_minutes: int
    quality: ReadingQuality
    fetched_at: datetime

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        start_time: datetime,
        end_time: datetime,
        energy_kwh: float,
        source: SourceName,
        source_resolution_minutes: int,
        quality: ReadingQuality,
        fetched_at: datetime | None = None,
    ) -> IntervalReading:
        start = _aware_utc(start_time)
        end = _aware_utc(end_time)
        duration_hours = (end - start).total_seconds() / 3600
        if not account_id:
            raise ValueError("account_id is required")
        if duration_hours <= 0:
            raise ValueError("interval end must be after interval start")
        if energy_kwh < 0:
            raise ValueError("energy_kwh cannot be negative")
        if source_resolution_minutes <= 0:
            raise ValueError("source resolution must be positive")
        return cls(
            account_id=account_id,
            start_time=start,
            end_time=end,
            energy_kwh=float(energy_kwh),
            average_power_w=float(energy_kwh) * 1000 / duration_hours,
            source=source,
            source_resolution_minutes=source_resolution_minutes,
            quality=quality,
            fetched_at=_aware_utc(fetched_at or datetime.now(UTC)),
        )

    def attributes(self) -> dict[str, str | int]:
        return {
            "interval_start": self.start_time.isoformat(),
            "interval_end": self.end_time.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "source": self.source.value,
            "source_resolution_minutes": self.source_resolution_minutes,
            "quality": self.quality.value,
        }


@dataclass(frozen=True, slots=True)
class DailyUsageReading:
    account_id: str
    start_time: datetime
    end_time: datetime
    energy_kwh: float
    fetched_at: datetime

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        start_time: datetime,
        end_time: datetime,
        energy_kwh: float,
        fetched_at: datetime | None = None,
    ) -> DailyUsageReading:
        if not account_id:
            raise ValueError("account_id is required")
        if energy_kwh < 0:
            raise ValueError("energy_kwh cannot be negative")
        start, end = _aware_utc(start_time), _aware_utc(end_time)
        if end <= start:
            raise ValueError("daily interval end must be after interval start")
        return cls(
            account_id, start, end, float(energy_kwh), _aware_utc(fetched_at or datetime.now(UTC))
        )


@dataclass(frozen=True, slots=True)
class DailyWeatherReading:
    account_id: str
    premise_uuid: str
    start_time: datetime
    end_time: datetime
    minimum_temperature_f: float | None
    mean_temperature_f: float | None
    maximum_temperature_f: float | None
    fetched_at: datetime
