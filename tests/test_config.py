from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import patch

from coned_scraper.config import Settings


class SettingsTests(unittest.TestCase):
    def test_existing_env_aliases_and_base64_password_are_supported(self) -> None:
        encoded = base64.b64encode(b"actual password\n").decode()
        environment = {
            "CONED_EMAIL": " user@example.com ",
            "CONED_PASSWORD": encoded,
            "CONED_PASSWORD_ENCODING": "base64",
            "TOTP_SECRET": "ABCD EFGH IJKL MNOP",
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_environment()

        self.assertEqual(" user@example.com ", settings.username)
        self.assertEqual("actual password", settings.password)
        self.assertEqual("ABCD EFGH IJKL MNOP", settings.totp_secret)

    def test_invalid_base64_password_fails_without_echoing_value(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"CONED_PASSWORD": "not base64!", "CONED_PASSWORD_ENCODING": "base64"},
                clear=True,
            ),
            self.assertRaisesRegex(ValueError, "not valid Base64"),
        ):
            Settings.from_environment()
