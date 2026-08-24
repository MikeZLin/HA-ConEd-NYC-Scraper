from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .polling import Poller
from .service import RefreshService
from .sources.opower import OpowerSource
from .sources.website import WebsiteApiSource
from .storage import ReadingStore


@dataclass(slots=True)
class Runtime:
    settings: Settings
    store: ReadingStore
    refresh_service: RefreshService
    poller: Poller

    @classmethod
    def create(cls, settings: Settings) -> Runtime:
        settings.require_opower_credentials()
        store = ReadingStore(settings.database_path)
        service = RefreshService(
            store,
            website=WebsiteApiSource(),
            opower=OpowerSource(
                settings.username,
                settings.password,
                settings.totp_secret,
            ),
        )
        return cls(
            settings=settings,
            store=store,
            refresh_service=service,
            poller=Poller(service, settings.refresh, settings.polling_interval_minutes),
        )

    def close(self) -> None:
        self.store.close()
