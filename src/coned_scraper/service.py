from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .models import IntervalReading
from .storage import ReadingStore

LOGGER = logging.getLogger(__name__)


class SourceMode(StrEnum):
    AUTO = "auto"
    WEBSITE_API = "website_api"
    OPOWER = "opower"


class SourceError(RuntimeError):
    """A retryable or fallback-eligible upstream source failure."""

    def __init__(self, message: str, *, stage: str = "source") -> None:
        super().__init__(message)
        self.stage = stage


class AccountOverrideError(RuntimeError):
    """A fatal account override mismatch."""


class UsageSource(Protocol):
    async def fetch(self, account_override: str | None) -> list[IntervalReading]: ...


@dataclass(frozen=True, slots=True)
class RefreshConfig:
    mode: SourceMode = SourceMode.AUTO
    account_override: str | None = None


class RefreshService:
    def __init__(
        self,
        store: ReadingStore,
        *,
        website: UsageSource,
        opower: UsageSource,
    ) -> None:
        self.store = store
        self.website = website
        self.opower = opower

    async def refresh(self, config: RefreshConfig) -> IntervalReading:
        if config.mode is SourceMode.WEBSITE_API:
            return await self._fetch_and_store(self.website, config.account_override)
        if config.mode is SourceMode.OPOWER:
            return await self._fetch_and_store(self.opower, config.account_override)

        try:
            return await self._fetch_and_store(self.website, config.account_override)
        except AccountOverrideError:
            raise
        except SourceError as error:
            LOGGER.warning(
                "Interval refresh source=website_api stage=%s fallback=true error=%s",
                error.stage,
                error.__class__.__name__,
            )
            return await self._fetch_and_store(self.opower, config.account_override)

    async def _fetch_and_store(
        self,
        source: UsageSource,
        account_override: str | None,
    ) -> IntervalReading:
        readings = await source.fetch(account_override)
        if not readings:
            raise SourceError("source returned no interval readings", stage="normalize")
        self.store.upsert_many(readings)
        return max(readings, key=lambda reading: reading.end_time)
