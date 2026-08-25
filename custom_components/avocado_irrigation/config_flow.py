"""Config flow for Avocado Irrigation."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import (
    CONF_IRRIGATION_VALVE,
    CONF_NAME,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PUMP_POWER,
    CONF_RAIN_GAUGE,
    DEFAULT_NAME,
    DOMAIN,
)


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
                    vol.Required(CONF_IRRIGATION_VALVE): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="switch")
                    ),
                    vol.Required(CONF_RAIN_GAUGE): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["binary_sensor", "sensor", "counter"]
                        )
                    ),
                    vol.Optional(CONF_PUMP_POWER): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_OUTDOOR_TEMPERATURE): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
        )
