"""Fix buttons in Settings -> System -> Repairs (1.7.0).

A few of ZoneFlow's repairs can be fixed on the spot instead of sending the
person off to Configure: pick another phone, swap a sensor that has gone for
a new one (or take it away), and set the flow rate from a measured run.
Home Assistant shows these as a "Fix" button on the repair.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from . import calibration
from .const import (
    CONF_FLOW_METER_ENTITY,
    CONF_INSIDE_TEMP_ENTITY,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)

# sensor role (issues.SENSOR_ROLES) -> (the setting that holds it, what can replace it)
SENSOR_SETTINGS: dict[str, tuple[str, selector.EntitySelectorConfig]] = {
    "temperature": (CONF_OUTDOOR_TEMP_ENTITY, selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
    "rain_gauge": (CONF_RAIN_COUNTER_ENTITY, selector.EntitySelectorConfig(domain=["counter", "sensor"])),
    "soil_moisture": (CONF_SOIL_MOISTURE_ENTITY, selector.EntitySelectorConfig(domain="sensor")),
    "pump_power": (CONF_PUMP_POWER_ENTITY, selector.EntitySelectorConfig(domain="sensor")),
    "flow_meter": (CONF_FLOW_METER_ENTITY, selector.EntitySelectorConfig(domain="sensor")),
    "weather": (CONF_WEATHER_ENTITY, selector.EntitySelectorConfig(domain="weather")),
}


class _Fix(RepairsFlow):
    def __init__(self, data: dict[str, Any]) -> None:
        self._entry_id = str(data.get("entry_id", ""))
        self._data = data

    @property
    def _entry(self):
        return self.hass.config_entries.async_get_entry(self._entry_id)

    @property
    def _controller(self):
        return self.hass.data.get(DOMAIN, {}).get(self._entry_id)

    def _gone(self):
        return self.async_abort(reason="zone_gone")

    def _owner_of(self, entry, key):
        """The entry the setting lives in: the zone's own, or -- when the zone
        takes it from its area -- the area's."""
        merged = {**entry.data, **entry.options}
        if merged.get(key):
            return entry
        area = getattr(self._controller, "area", None)
        return area.entry if area is not None else entry


class NotifyFix(_Fix):
    """The phone no longer exists: pick another, or none."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        entry = self._entry
        if entry is None:
            return self._gone()
        if user_input is not None:
            target = self._owner_of(entry, CONF_NOTIFY_ENTITY)  # an area's phone is fixed on the area
            self.hass.config_entries.async_update_entry(
                target, options={**target.options, CONF_NOTIFY_ENTITY: user_input.get(CONF_NOTIFY_ENTITY) or None}
            )
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_NOTIFY_ENTITY): selector.EntitySelector(selector.EntitySelectorConfig(domain="notify"))}
            ),
            description_placeholders={"zone": entry.title, "entity": str(self._data.get("entity", ""))},
        )


class SensorFix(_Fix):
    """A sensor has been offline for days: pick its replacement, or take it away."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        entry = self._entry
        role = str(self._data.get("role", ""))
        if entry is None or role not in SENSOR_SETTINGS:
            return self._gone()
        key, config = SENSOR_SETTINGS[role]
        controller = self._controller
        if role == "temperature" and controller is not None and not controller.is_outdoor:
            key = CONF_INSIDE_TEMP_ENTITY  # a greenhouse waters by its inside sensor: that is the one that went
        if user_input is not None:
            target = self._owner_of(entry, key)
            replacement = user_input.get("replacement") or None
            self.hass.config_entries.async_update_entry(target, options={**target.options, key: replacement})
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Optional("replacement"): selector.EntitySelector(config)}),
            description_placeholders={"zone": entry.title, "entity": str(self._data.get("entity", ""))},
        )


class FlowRateFix(_Fix):
    """The flow rate was never set: run the valve, then enter what came out."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        controller = self._controller
        if controller is None:
            return self._gone()
        if user_input is not None:
            if user_input.get("run"):
                try:
                    await controller.start_service_run(15)
                except HomeAssistantError:
                    return self.async_abort(reason="zone_busy")
            return await self.async_step_measure()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required("run", default=True): bool}),
            description_placeholders={"zone": controller.entry.title},
        )

    async def async_step_measure(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        controller = self._controller
        if controller is None:
            return self._gone()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await calibration.calibrate_from_volume(
                    controller, float(user_input["volume"]), float(user_input["area"]), float(user_input["minutes"])
                )
            except HomeAssistantError:
                errors["base"] = "out_of_range"
            else:
                return self.async_create_entry(data={})
        imperial = controller.imperial
        number = selector.NumberSelector
        config = selector.NumberSelectorConfig
        return self.async_show_form(
            step_id="measure",
            data_schema=vol.Schema(
                {
                    vol.Required("volume"): number(config(min=0.01, max=1000000, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="gal" if imperial else "L")),
                    vol.Required("area"): number(config(min=0.1, max=100000, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="ft²" if imperial else "m²")),
                    vol.Required("minutes", default=15): number(config(min=1, max=240, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="min")),
                }
            ),
            errors=errors,
            description_placeholders={"zone": controller.entry.title},
        )


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    kind = (data or {}).get("kind")
    flows = {"notify": NotifyFix, "sensor": SensorFix, "flow_rate": FlowRateFix}
    return flows[kind](data or {})
