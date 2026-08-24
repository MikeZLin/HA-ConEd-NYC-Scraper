from __future__ import annotations

import csv
import io
import unittest

from coned_scraper.api import _import_statistics_csv


class StatisticsExportTests(unittest.TestCase):
    def test_mixed_csv_contains_cumulative_energy_and_temperature(self) -> None:
        source = [
            {
                "start_time": "2026-08-22T04:00:00+00:00",
                "energy_kwh": 12.5,
                "temperature_min_f": 65.0,
                "temperature_mean_f": 72.0,
                "temperature_max_f": 80.0,
            },
            {
                "start_time": "2026-08-23T04:00:00+00:00",
                "energy_kwh": 8.25,
                "temperature_min_f": None,
                "temperature_mean_f": None,
                "temperature_max_f": None,
            },
        ]

        rows = list(csv.DictReader(io.StringIO(_import_statistics_csv(source))))

        self.assertEqual(
            [
                "sensor:coned_imported_energy",
                "sensor:coned_imported_temperature",
                "sensor:coned_imported_energy",
            ],
            [row["statistic_id"] for row in rows],
        )
        self.assertEqual("2026-08-22 00:00", rows[0]["start"])
        self.assertEqual("12.5", rows[0]["sum"])
        self.assertEqual("20.75", rows[2]["sum"])
        self.assertEqual("72", rows[1]["mean"])
        self.assertEqual("°F", rows[1]["unit"])


if __name__ == "__main__":
    unittest.main()
