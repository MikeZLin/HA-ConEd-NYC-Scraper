from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from coned_scraper.models import ReadingQuality, SourceName
from coned_scraper.sources.opower import OpowerSource, normalize_opower_reads


class OpowerNormalizationTests(unittest.TestCase):
    def test_totp_secret_formatting_whitespace_is_normalized(self) -> None:
        source = OpowerSource(" user@example.com ", "password", "abcd efgh ijkl mnop")

        self.assertEqual("user@example.com", source.username)
        self.assertEqual("ABCDEFGHIJKLMNOP", source.totp_secret)

    def test_hourly_read_is_split_into_four_labeled_estimates(self) -> None:
        start = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        reads = [
            SimpleNamespace(
                start_time=start,
                end_time=start + timedelta(hours=1),
                consumption=1.2,
            )
        ]

        result = normalize_opower_reads(reads, account_id="acct", native_minutes=60)

        self.assertEqual(4, len(result))
        self.assertEqual([0.3, 0.3, 0.3, 0.3], [item.energy_kwh for item in result])
        self.assertTrue(all(item.average_power_w == 1200.0 for item in result))
        self.assertTrue(all(item.quality is ReadingQuality.ESTIMATED for item in result))
        self.assertTrue(all(item.source is SourceName.OPOWER for item in result))
        self.assertTrue(all(item.source_resolution_minutes == 60 for item in result))

    def test_native_quarter_hour_read_remains_measured(self) -> None:
        start = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        reads = [
            SimpleNamespace(
                start_time=start,
                end_time=start + timedelta(minutes=15),
                consumption=0.2,
            )
        ]

        result = normalize_opower_reads(reads, account_id="acct", native_minutes=15)

        self.assertEqual(1, len(result))
        self.assertEqual(ReadingQuality.MEASURED, result[0].quality)
        self.assertEqual(800.0, result[0].average_power_w)


if __name__ == "__main__":
    unittest.main()
