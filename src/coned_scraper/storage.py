from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .models import IntervalReading, ReadingQuality, SourceName


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

    def latest_payload(self) -> dict[str, object] | None:
        item = self.latest()
        if item is None:
            return None
        return {
            "interval_energy_kwh": item.energy_kwh,
            "interval_average_power_w": item.average_power_w,
            "attributes": item.attributes(),
        }


def _precedence(quality: str, source: str) -> int:
    if quality == ReadingQuality.ESTIMATED.value:
        return 1
    if source == SourceName.WEBSITE_API.value:
        return 3
    return 2
