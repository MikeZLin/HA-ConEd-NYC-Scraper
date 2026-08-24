from __future__ import annotations

from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL


class ConEdisonIntervalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api_url: str) -> None:
        super().__init__(hass, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api_url = api_url.rstrip("/")

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{self.api_url}/api/meter-reading/latest",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status != 200:
                    raise UpdateFailed(f"Collector returned HTTP {response.status}")
                return await response.json()
        except aiohttp.ClientError as error:
            raise UpdateFailed("Unable to reach the Con Edison collector") from error
