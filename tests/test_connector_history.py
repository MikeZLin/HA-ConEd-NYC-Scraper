import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _load_history_module() -> Any:
    path = Path(__file__).parents[1] / "custom_components/coned_connect/history.py"
    spec = importlib.util.spec_from_file_location("coned_connect_history", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(start: str, end: str, energy: float, power: float) -> dict[str, object]:
    return {
        "start_time": start,
        "end_time": end,
        "energy_kwh": energy,
        "average_power_w": power,
    }


def test_hourly_usage_sums_complete_intervals_and_tracks_cumulative_energy() -> None:
    history = _load_history_module()
    rows = [
        _row(f"2026-08-24T{hour}:{minute:02d}:00+00:00", end, energy, power)
        for hour, minute, end, energy, power in (
            (16, 0, "2026-08-24T16:15:00+00:00", 0.114, 114),
            (16, 15, "2026-08-24T16:30:00+00:00", 0.120, 120),
            (16, 30, "2026-08-24T16:45:00+00:00", 0.105, 105),
            (16, 45, "2026-08-24T17:00:00+00:00", 0.130, 130),
            (17, 0, "2026-08-24T17:30:00+00:00", 0.200, 400),
            (17, 30, "2026-08-24T18:00:00+00:00", 0.300, 600),
        )
    ]

    result = history.hourly_usage(rows)

    assert [item.start for item in result] == [
        datetime(2026, 8, 24, 16, tzinfo=UTC),
        datetime(2026, 8, 24, 17, tzinfo=UTC),
    ]
    assert result[0].energy_kwh == 0.469
    assert result[0].average_power_w == 469
    assert result[0].cumulative_energy_kwh == 0.469
    assert result[1].energy_kwh == 0.5
    assert result[1].average_power_w == 500
    assert result[1].cumulative_energy_kwh == 0.969


def test_hourly_usage_omits_incomplete_or_overlapping_hours() -> None:
    history = _load_history_module()
    rows = [
        _row("2026-08-24T16:00:00+00:00", "2026-08-24T16:15:00+00:00", 0.1, 100),
        _row("2026-08-24T16:30:00+00:00", "2026-08-24T17:00:00+00:00", 0.2, 200),
        _row("2026-08-24T17:00:00+00:00", "2026-08-24T18:15:00+00:00", 0.3, 300),
    ]

    assert history.hourly_usage(rows) == []


def test_daily_usage_sorts_rows_and_tracks_cumulative_energy() -> None:
    history = _load_history_module()
    rows = [
        {"start_time": "2026-08-24T04:00:00+00:00", "energy_kwh": 7.25},
        {"start_time": "2026-08-23T04:00:00+00:00", "energy_kwh": 23.28},
    ]

    result = history.daily_usage(rows)

    assert [item.start for item in result] == [
        datetime(2026, 8, 23, 4, tzinfo=UTC),
        datetime(2026, 8, 24, 4, tzinfo=UTC),
    ]
    assert [item.energy_kwh for item in result] == [23.28, 7.25]
    assert [item.cumulative_energy_kwh for item in result] == [23.28, 30.53]


def test_daily_usage_ignores_invalid_rows() -> None:
    history = _load_history_module()
    rows = [
        {"start_time": "2026-08-24T04:15:00+00:00", "energy_kwh": 2},
        {"start_time": "2026-08-24T04:00:00+00:00", "energy_kwh": -1},
        {"start_time": "not-a-date", "energy_kwh": 3},
    ]

    assert history.daily_usage(rows) == []
