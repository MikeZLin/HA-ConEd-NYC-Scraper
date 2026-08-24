from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoginCredentials:
    username: str
    password: str
    totp_secret: str

    def validate(self) -> None:
        if not self.username.strip():
            raise ValueError("username is required")
        if not self.password:
            raise ValueError("password is required")
        if not "".join(self.totp_secret.split()):
            raise ValueError("TOTP secret is required")


class EncryptedCredentialStore:
    """Fernet-encrypted login data stored in the persistent data directory."""

    def __init__(self, data_directory: str | Path) -> None:
        self.directory = Path(data_directory)
        self.key_path = self.directory / "login.key"
        self.login_path = self.directory / "login.enc"

    def initialize(self) -> None:
        from cryptography.fernet import Fernet

        self.directory.mkdir(parents=True, exist_ok=True)
        _ensure_private_directory(self.directory)
        if not self.key_path.exists():
            _write_private(self.key_path, Fernet.generate_key())

    def load(self) -> LoginCredentials | None:
        if not self.login_path.exists():
            return None
        from cryptography.fernet import Fernet, InvalidToken

        try:
            payload = Fernet(self.key_path.read_bytes()).decrypt(self.login_path.read_bytes())
            decoded = cast(dict[str, Any], json.loads(payload))
            credentials = LoginCredentials(
                username=str(decoded["username"]),
                password=str(decoded["password"]),
                totp_secret=str(decoded["totp_secret"]),
            )
            credentials.validate()
            return credentials
        except (InvalidToken, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("encrypted login file cannot be decrypted") from error

    def save(self, credentials: LoginCredentials) -> None:
        from cryptography.fernet import Fernet

        credentials.validate()
        payload = json.dumps(
            {
                "username": credentials.username.strip(),
                "password": credentials.password,
                "totp_secret": "".join(credentials.totp_secret.split()).upper(),
            },
            separators=(",", ":"),
        ).encode()
        encrypted = Fernet(self.key_path.read_bytes()).encrypt(payload)
        _write_private(self.login_path, encrypted)

def _ensure_private_directory(path: Path) -> None:
    try:
        path.chmod(0o700)
    except PermissionError:
        LOGGER.warning("Unable to restrict data directory permissions")


def _write_private(path: Path, value: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
