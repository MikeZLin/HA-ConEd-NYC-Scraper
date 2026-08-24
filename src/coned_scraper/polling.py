from __future__ import annotations

import asyncio
import logging

from .service import AccountOverrideError, RefreshConfig, RefreshService, SourceError

LOGGER = logging.getLogger(__name__)


class Poller:
    def __init__(
        self,
        service: RefreshService,
        config: RefreshConfig,
        interval_minutes: int,
    ) -> None:
        if interval_minutes < 15:
            raise ValueError("polling interval cannot be less than 15 minutes")
        self.service = service
        self.config = config
        self.interval_seconds = interval_minutes * 60
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="coned-interval-poller")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.service.refresh(self.config)
            except AccountOverrideError:
                LOGGER.error("Interval polling stopped: invalid account override")
                return
            except SourceError as error:
                LOGGER.error(
                    "Interval polling failed stage=%s retry=true error=%s",
                    error.stage,
                    error.__class__.__name__,
                )
            await asyncio.sleep(self.interval_seconds)
