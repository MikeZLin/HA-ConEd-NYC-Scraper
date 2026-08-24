from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from coned_scraper.models import IntervalReading, ReadingQuality, SourceName
from coned_scraper.service import (
    AccountOverrideError,
    RefreshConfig,
    RefreshService,
    SourceError,
    SourceMode,
)
from coned_scraper.storage import ReadingStore

START = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def reading(
    *,
    source: SourceName = SourceName.WEBSITE_API,
    quality: ReadingQuality = ReadingQuality.MEASURED,
    energy_kwh: float = 0.25,
    minutes: int = 15,
    source_resolution_minutes: int = 15,
) -> IntervalReading:
    return IntervalReading.create(
        account_id="acct-1",
        start_time=START,
        end_time=START + timedelta(minutes=minutes),
        energy_kwh=energy_kwh,
        source=source,
        source_resolution_minutes=source_resolution_minutes,
        quality=quality,
        fetched_at=START + timedelta(hours=2),
    )


class FakeSource:
    def __init__(
        self,
        readings: list[IntervalReading] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.readings = readings or []
        self.error = error
        self.calls: list[str | None] = []

    async def fetch(self, account_override: str | None) -> list[IntervalReading]:
        self.calls.append(account_override)
        if self.error:
            raise self.error
        return self.readings


class RefreshUsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = ReadingStore(Path(self.tempdir.name) / "readings.sqlite3")

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def run_refresh(
        self,
        website: FakeSource,
        opower: FakeSource,
        config: RefreshConfig,
    ) -> IntervalReading:
        service = RefreshService(self.store, website=website, opower=opower)
        return asyncio.run(service.refresh(config))

    def test_auto_prefers_website_and_persists_home_assistant_payload(self) -> None:
        website = FakeSource([reading()])
        opower = FakeSource([reading(source=SourceName.OPOWER)])

        result = self.run_refresh(website, opower, RefreshConfig(mode=SourceMode.AUTO))

        self.assertEqual(SourceName.WEBSITE_API, result.source)
        self.assertEqual([], opower.calls)
        self.assertEqual(1000.0, result.average_power_w)
        self.assertEqual(
            {
                "interval_energy_kwh": 0.25,
                "interval_average_power_w": 1000.0,
                "attributes": {
                    "interval_start": "2026-08-23T12:00:00+00:00",
                    "interval_end": "2026-08-23T12:15:00+00:00",
                    "fetched_at": "2026-08-23T14:00:00+00:00",
                    "source": "website_api",
                    "source_resolution_minutes": 15,
                    "quality": "measured",
                },
            },
            self.store.latest_payload(),
        )

    def test_auto_falls_back_to_opower_on_source_error(self) -> None:
        website = FakeSource(error=SourceError("session expired"))
        opower_reading = reading(source=SourceName.OPOWER)
        opower = FakeSource([opower_reading])

        result = self.run_refresh(website, opower, RefreshConfig(mode=SourceMode.AUTO))

        self.assertEqual(opower_reading, result)
        self.assertEqual([None], opower.calls)

    def test_explicit_mode_does_not_fall_back_and_cached_value_survives(self) -> None:
        self.store.upsert_many([reading()])
        website = FakeSource(error=SourceError("upstream unavailable"))
        opower = FakeSource([reading(source=SourceName.OPOWER)])

        with self.assertRaisesRegex(SourceError, "upstream unavailable"):
            self.run_refresh(
                website,
                opower,
                RefreshConfig(mode=SourceMode.WEBSITE_API),
            )

        self.assertEqual([], opower.calls)
        self.assertEqual(SourceName.WEBSITE_API, self.store.latest().source)  # type: ignore[union-attr]

    def test_invalid_account_override_is_fatal_even_in_auto_mode(self) -> None:
        website = FakeSource(error=AccountOverrideError("unknown account"))
        opower = FakeSource([reading(source=SourceName.OPOWER)])

        with self.assertRaisesRegex(AccountOverrideError, "unknown account"):
            self.run_refresh(
                website,
                opower,
                RefreshConfig(mode=SourceMode.AUTO, account_override="missing"),
            )

        self.assertEqual([], opower.calls)

    def test_estimate_can_be_replaced_by_measured_but_not_the_reverse(self) -> None:
        estimated = reading(
            source=SourceName.OPOWER,
            quality=ReadingQuality.ESTIMATED,
            source_resolution_minutes=60,
        )
        measured = reading()

        self.store.upsert_many([estimated])
        self.store.upsert_many([measured])
        self.store.upsert_many([estimated])

        latest = self.store.latest()
        self.assertIsNotNone(latest)
        self.assertEqual(ReadingQuality.MEASURED, latest.quality)  # type: ignore[union-attr]
        self.assertEqual(SourceName.WEBSITE_API, latest.source)  # type: ignore[union-attr]

    def test_opower_measured_does_not_replace_website_measured(self) -> None:
        website = reading()
        opower = reading(source=SourceName.OPOWER)

        self.store.upsert_many([website])
        self.store.upsert_many([opower])

        latest = self.store.latest()
        self.assertIsNotNone(latest)
        self.assertEqual(SourceName.WEBSITE_API, latest.source)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
