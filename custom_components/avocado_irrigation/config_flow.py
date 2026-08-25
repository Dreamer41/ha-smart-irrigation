"""Config flow for Avocado Irrigation."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import DEFAULT_NAME, DOMAIN


class AvocadoIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Avocado Irrigation config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial setup step."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                }
            ),
        )
