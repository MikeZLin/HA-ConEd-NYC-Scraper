from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_API_URL, DEFAULT_API_URL, DOMAIN


class ConEdisonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_API_URL].rstrip("/"))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Con Edison Interval Usage", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_URL, default=DEFAULT_API_URL): str}
            ),
        )
