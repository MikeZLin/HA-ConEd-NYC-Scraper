"""Convert collector intervals into Home Assistant hourly statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class HourlyUsage:
    """A complete UTC hour of interval usage."""

    start: datetime
    energy_kwh: float
    average_power_w: float
    cumulative_energy_kwh: float


def hourly_usage(rows: list[dict[str, Any]]) -> list[HourlyUsage]:
    """Aggregate additive interval readings into complete UTC hours."""
    intervals: list[tuple[datetime, datetime, float, float]] = []
    for row in rows:
        try:
            start = _parse_datetime(row["start_time"])
            end = _parse_datetime(row["end_time"])
            energy = float(row["energy_kwh"])
        except (KeyError, TypeError, ValueError):
            continue
        hour_end = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        if end <= start or end > hour_end:
            continue
        average_power = energy * 1000 / ((end - start).total_seconds() / 3600)
        intervals.append((start, end, energy, average_power))

    by_hour: dict[datetime, list[tuple[datetime, datetime, float, float]]] = {}
    for interval in intervals:
        hour = interval[0].replace(minute=0, second=0, microsecond=0)
        by_hour.setdefault(hour, []).append(interval)

    result: list[HourlyUsage] = []
    cumulative = 0.0
    for hour, items in sorted(by_hour.items()):
        items.sort(key=lambda item: item[0])
        cursor = hour
        duration = 0.0
        weighted_power = 0.0
        energy = 0.0
        valid = True
        for start, end, interval_energy, power in items:
            if start != cursor or end > hour + timedelta(hours=1):
                valid = False
                break
            seconds = (end - start).total_seconds()
            duration += seconds
            weighted_power += power * seconds
            energy += interval_energy
            cursor = end
        if not valid or cursor != hour + timedelta(hours=1) or duration != 3600:
            continue
        cumulative += energy
        result.append(
            HourlyUsage(
                start=hour,
                energy_kwh=energy,
                average_power_w=weighted_power / duration,
                cumulative_energy_kwh=cumulative,
            )
        )
    return result


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError
    return parsed.astimezone(UTC)
