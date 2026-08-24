from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from coned_scraper.api import create_app
from coned_scraper.config import Settings
from coned_scraper.service import RefreshConfig, SourceMode


class SettingsApiTests(unittest.TestCase):
    def test_unconfigured_service_starts_and_password_is_never_returned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_directory = Path(temporary) / "data"
            app = create_app(
                Settings(
                    data_directory=data_directory,
                    database_path=data_directory / "readings.sqlite3",
                    refresh=RefreshConfig(mode=SourceMode.AUTO),
                    username="person@example.com",
                    password="",
                    totp_secret="JBSWY3DP",
                )
            )
            health = asyncio.run(_endpoint(app, "/health")())
            settings = asyncio.run(_endpoint(app, "/api/settings")())

            self.assertEqual({"status": "ok", "configured": False}, health)
            self.assertEqual(False, settings["configured"])
            self.assertNotIn("password", settings)
            self.assertEqual("person@example.com", settings["username"])
            self.assertEqual("JBSWY3DP", settings["totp_secret"])
            with self.assertRaises(HTTPException) as totp_error:
                asyncio.run(_endpoint(app, "/api/settings/totp")())
            with self.assertRaises(HTTPException) as refresh_error:
                asyncio.run(_endpoint(app, "/api/meter-reading/refresh", "POST")())
            self.assertEqual(409, totp_error.exception.status_code)
            self.assertEqual(409, refresh_error.exception.status_code)


def _endpoint(app: Any, path: str, method: str = "GET") -> Any:
    for route in app.routes:
        if route.path == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"route not found: {method} {path}")


if __name__ == "__main__":
    unittest.main()
