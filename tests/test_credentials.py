from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from coned_scraper.credentials import EncryptedCredentialStore, LoginCredentials


class EncryptedCredentialStoreTests(unittest.TestCase):
    def test_round_trip_is_encrypted_and_files_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "data"
            store = EncryptedCredentialStore(directory)
            token = store.initialize()
            login = LoginCredentials("person@example.com", "correct horse", "JBSW Y3DP")

            store.save(login)

            self.assertEqual(
                LoginCredentials("person@example.com", "correct horse", "JBSWY3DP"),
                store.load(),
            )
            self.assertNotIn(b"correct horse", store.login_path.read_bytes())
            self.assertIsNone(token)
            self.assertEqual(0o700, stat.S_IMODE(directory.stat().st_mode))
            for path in (store.key_path, store.login_path):
                self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    def test_initialize_preserves_existing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EncryptedCredentialStore(temporary)
            store.initialize()
            key = store.key_path.read_bytes()

            self.assertIsNone(store.initialize())
            self.assertEqual(key, store.key_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
