from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from .models import (
    DailyUsageReading,
    DailyWeatherReading,
    IntervalReading,
    ReadingQuality,
    SourceName,
)


class ReadingStore:
    """SQLite-backed canonical interval store."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interval_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                energy_kwh REAL NOT NULL,
                average_power_w REAL NOT NULL,
                source TEXT NOT NULL,
                source_resolution_minutes INTEGER NOT NULL,
                quality TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                UNIQUE(account_id, start_time, end_time)
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS interval_readings_end_time ON interval_readings(end_time)"
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS daily_usage_readings (
                account_id TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                energy_kwh REAL NOT NULL, fetched_at TEXT NOT NULL,
                PRIMARY KEY(account_id, start_time, end_time)
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS daily_weather_readings (
                account_id TEXT NOT NULL, premise_uuid TEXT NOT NULL,
                start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                minimum_temperature_f REAL, mean_temperature_f REAL,
                maximum_temperature_f REAL, fetched_at TEXT NOT NULL,
                PRIMARY KEY(account_id, premise_uuid, start_time, end_time)
            )"""
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def upsert_many(self, readings: Iterable[IntervalReading]) -> None:
        with self._connection:
            for item in readings:
                existing = self._connection.execute(
                    """
                SELECT quality, source FROM interval_readings
                    WHERE account_id = ? AND start_time = ? AND end_time = ?
                    """,
                    (item.account_id, item.start_time.isoformat(), item.end_time.isoformat()),
                ).fetchone()
                if existing and _precedence(existing["quality"], existing["source"]) > _precedence(
                    item.quality.value, item.source.value
                ):
                    continue
                self._connection.execute(
                    """
                    INSERT INTO interval_readings (
                        account_id, start_time, end_time, energy_kwh, average_power_w,
                        source, source_resolution_minutes, quality, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, start_time, end_time) DO UPDATE SET
                        energy_kwh = excluded.energy_kwh,
                        average_power_w = excluded.average_power_w,
                        source = excluded.source,
                        source_resolution_minutes = excluded.source_resolution_minutes,
                        quality = excluded.quality,
                        fetched_at = excluded.fetched_at
                    """,
                    (
                        item.account_id,
                        item.start_time.isoformat(),
                        item.end_time.isoformat(),
                        item.energy_kwh,
                        item.average_power_w,
                        item.source.value,
                        item.source_resolution_minutes,
                        item.quality.value,
                        item.fetched_at.isoformat(),
                    ),
                )

    def latest(self) -> IntervalReading | None:
        row = self._connection.execute(
            """
            SELECT * FROM interval_readings
            ORDER BY end_time DESC, fetched_at DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return IntervalReading(
            account_id=row["account_id"],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]),
            energy_kwh=float(row["energy_kwh"]),
            average_power_w=float(row["average_power_w"]),
            source=SourceName(row["source"]),
            source_resolution_minutes=int(row["source_resolution_minutes"]),
            quality=ReadingQuality(row["quality"]),
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )

    def upsert_daily_usage(self, readings: Iterable[DailyUsageReading]) -> None:
        with self._connection:
            self._connection.executemany(
                """INSERT INTO daily_usage_readings
                   (account_id, start_time, end_time, energy_kwh, fetched_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(account_id, start_time, end_time) DO UPDATE SET
                     energy_kwh=excluded.energy_kwh, fetched_at=excluded.fetched_at""",
                [
                    (
                        r.account_id,
                        r.start_time.isoformat(),
                        r.end_time.isoformat(),
                        r.energy_kwh,
                        r.fetched_at.isoformat(),
                    )
                    for r in readings
                ],
            )

    def upsert_daily_weather(self, readings: Iterable[DailyWeatherReading]) -> None:
        with self._connection:
            self._connection.executemany(
                """INSERT INTO daily_weather_readings
                   (account_id, premise_uuid, start_time, end_time,
                    minimum_temperature_f, mean_temperature_f,
                    maximum_temperature_f, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(account_id, premise_uuid, start_time, end_time) DO UPDATE SET
                     minimum_temperature_f=excluded.minimum_temperature_f,
                     mean_temperature_f=excluded.mean_temperature_f,
                     maximum_temperature_f=excluded.maximum_temperature_f,
                     fetched_at=excluded.fetched_at""",
                [
                    (
                        r.account_id,
                        r.premise_uuid,
                        r.start_time.isoformat(),
                        r.end_time.isoformat(),
                        r.minimum_temperature_f,
                        r.mean_temperature_f,
                        r.maximum_temperature_f,
                        r.fetched_at.isoformat(),
                    )
                    for r in readings
                ],
            )

    def latest_payload(self) -> dict[str, object] | None:
        item = self.latest()
        if item is None:
            return None
        return {
            "interval_energy_kwh": item.energy_kwh,
            "interval_average_power_w": item.average_power_w,
            "attributes": item.attributes(),
        }

    def dashboard_status(self) -> dict[str, object]:
        item = self.latest()
        if item is None:
            return {"last_scraped_at": None, "latest_interval_end": None, "source": None}
        return {
            "last_scraped_at": item.fetched_at.isoformat(),
            "latest_interval_end": item.end_time.isoformat(),
            "source": item.source.value,
        }

    def interval_history_payload(self, *, hours: int | None = 24) -> list[dict[str, object]]:
        latest = self.latest()
        if latest is None:
            return []
        cutoff = latest.end_time - timedelta(hours=hours) if hours is not None else None
        rows = self._connection.execute(
            """SELECT start_time, end_time, energy_kwh, average_power_w, source, quality
               FROM interval_readings WHERE account_id = ? ORDER BY end_time ASC""",
            (latest.account_id,),
        ).fetchall()
        return [
            {
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "energy_kwh": float(row["energy_kwh"]),
                "average_power_w": float(row["average_power_w"]),
                "source": row["source"],
                "quality": row["quality"],
            }
            for row in rows
            if cutoff is None or datetime.fromisoformat(row["end_time"]) > cutoff
        ]

    def daily_history_payload(self, *, days: int | None = 31) -> list[dict[str, object]]:
        latest = self.latest()
        if latest is None:
            return []
        usage_query = """SELECT start_time, end_time, energy_kwh FROM daily_usage_readings
                         WHERE account_id = ? ORDER BY start_time DESC"""
        weather_query = """SELECT start_time, minimum_temperature_f, mean_temperature_f,
                                   maximum_temperature_f FROM daily_weather_readings
                            WHERE account_id = ? ORDER BY start_time DESC"""
        if days is None:
            usage_rows = self._connection.execute(usage_query, (latest.account_id,)).fetchall()
            weather_rows = self._connection.execute(weather_query, (latest.account_id,)).fetchall()
        else:
            usage_rows = self._connection.execute(
                f"{usage_query} LIMIT ?", (latest.account_id, days)
            ).fetchall()
            weather_rows = self._connection.execute(
                f"{weather_query} LIMIT ?", (latest.account_id, days + 2)
            ).fetchall()
        weather_by_date = {
            datetime.fromisoformat(row["start_time"]).date().isoformat(): row
            for row in weather_rows
        }
        result: list[dict[str, object]] = []
        for row in reversed(usage_rows):
            day = datetime.fromisoformat(row["start_time"]).date().isoformat()
            weather = weather_by_date.get(day)
            result.append(
                {
                    "date": day,
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "energy_kwh": float(row["energy_kwh"]),
                    "temperature_min_f": _nullable_float(weather, "minimum_temperature_f"),
                    "temperature_mean_f": _nullable_float(weather, "mean_temperature_f"),
                    "temperature_max_f": _nullable_float(weather, "maximum_temperature_f"),
                }
            )
        return result


def _precedence(quality: str, source: str) -> int:
    if quality == ReadingQuality.ESTIMATED.value:
        return 1
    if source == SourceName.WEBSITE_API.value:
        return 3
    return 2


def _nullable_float(row: sqlite3.Row | None, key: str) -> float | None:
    if row is None or row[key] is None:
        return None
    return float(row[key])
