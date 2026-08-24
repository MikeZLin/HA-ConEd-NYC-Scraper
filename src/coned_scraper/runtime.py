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
    def create(cls, settings: Settings, *, store: ReadingStore | None = None) -> Runtime:
        settings.require_opower_credentials()
        reading_store = store or ReadingStore(settings.database_path)
        service = RefreshService(
            reading_store,
            website=WebsiteApiSource(
                settings.username,
                settings.password,
                settings.totp_secret,
                daily_lookback_days=settings.daily_lookback_days,
            ),
            opower=OpowerSource(
                settings.username,
                settings.password,
                settings.totp_secret,
            ),
        )
        return cls(
            settings=settings,
            store=reading_store,
            refresh_service=service,
            poller=Poller(service, settings.refresh, settings.polling_interval_minutes),
        )

    def close(self) -> None:
        self.store.close()

    async def aclose(self, *, close_store: bool = True) -> None:
        website = self.refresh_service.website
        if isinstance(website, WebsiteApiSource):
            await website.close()
        if close_store:
            self.close()
