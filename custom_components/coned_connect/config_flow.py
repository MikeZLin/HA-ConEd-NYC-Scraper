from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_API_PORT,
    CONF_API_URL,
    DEFAULT_API_PORT,
    DEFAULT_API_URL,
    DOMAIN,
    build_api_url,
)


class ConEdisonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                collector_url = build_api_url(user_input[CONF_API_URL], user_input[CONF_API_PORT])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                await self.async_set_unique_id(collector_url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Con Edison Interval Usage",
                    data={
                        CONF_API_URL: user_input[CONF_API_URL].strip().rstrip("/"),
                        CONF_API_PORT: user_input[CONF_API_PORT],
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_URL, default=DEFAULT_API_URL): str,
                    vol.Required(CONF_API_PORT, default=DEFAULT_API_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                }
            ),
            errors=errors,
        )
