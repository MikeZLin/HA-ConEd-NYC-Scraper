from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .service import RefreshConfig, SourceMode


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    refresh: RefreshConfig
    username: str
    password: str
    totp_secret: str
    polling_interval_minutes: int = 15

    @classmethod
    def from_environment(cls) -> Settings:
        raw_mode = os.getenv("CONED_SOURCE_MODE", SourceMode.AUTO.value)
        try:
            mode = SourceMode(raw_mode)
        except ValueError as error:
            choices = ", ".join(mode.value for mode in SourceMode)
            raise ValueError(f"CONED_SOURCE_MODE must be one of: {choices}") from error
        account_override = os.getenv("CONED_ACCOUNT_OVERRIDE") or None
        polling_interval = int(os.getenv("CONED_POLLING_INTERVAL_MINUTES", "15"))
        if polling_interval < 15:
            raise ValueError("CONED_POLLING_INTERVAL_MINUTES cannot be less than 15")
        return cls(
            database_path=Path(os.getenv("CONED_DATABASE_PATH", "data/readings.sqlite3")),
            refresh=RefreshConfig(mode=mode, account_override=account_override),
            username=os.getenv("CONED_USERNAME", ""),
            password=os.getenv("CONED_PASSWORD", ""),
            totp_secret=os.getenv("CONED_TOTP_SECRET", ""),
            polling_interval_minutes=polling_interval,
        )

    def require_opower_credentials(self) -> None:
        if not all((self.username, self.password, self.totp_secret)):
            raise ValueError("CONED_USERNAME, CONED_PASSWORD, and CONED_TOTP_SECRET are required")
