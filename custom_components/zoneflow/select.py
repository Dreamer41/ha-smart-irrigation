"""Live dashboard dropdowns for two things that previously required going
through Settings -> Devices & Services -> Configure (soil type) or waiting
on the planting date (growth stage):

- ZoneFlowSoilTypeSelect: an instant override of the zone's soil type,
  read by ZoneFlowController.soil_type (controller.py) ahead of the
  config-flow/options value. Every place that reads soil_type today
  (currently just the informational ZoneFlowSoilProfileSensor) picks this
  up automatically, with no reload of the config entry needed -- unlike
  changing it via Options, which reloads the whole zone.

- ZoneFlowGrowthStageSelect: named presets ("Seedling", "Fruiting", ...)
  that jump the paired "Growth Stage Manual Override" number (a plain
  NUMBER_DEFS slider, see number.py/const.py) to a representative
  percentage and switch growth_ramp_fraction() (controller.py) over to
  using it instead of the planting-date curve. Picking "Auto" goes back to
  the curve; picking "Manual" leaves whatever the slider is currently at
  in effect, for fine-tuning beyond the presets. Both are pure convenience
  layers -- see const.py's GROWTH_STAGE_MODE_* comment for why "off"
  (growth-ramp profile) still always wins.

- ZoneFlowGrowthRampProfileSelect: an instant override of WHICH curve this
  zone follows (Off / Fast Annual / Slow Fruiting / Established Perennial /
  Custom), read by ZoneFlowController.growth_ramp_profile ahead of the
  config-flow/options value -- same no-reload pattern as soil type. Switch
  a zone to "Custom" here, then dial in its own curve on the
  "growth_ramp_custom_*" number sliders (const.py/number.py) for a
  plant-specific ramp that doesn't have to fit one of the three presets.

- ZoneFlowHealthSelect: a pure human journal field (Excellent / Good /
  Poor / Sick) for tracking how the zone's plant is actually doing over
  time -- see const.py's HEALTH_STATUS_OPTIONS comment. Nothing in the
  controller reads this; it exists purely for a person (or anyone else
  who tends the zone) to record their own observation, paired with the
  free-text notes field in text.py.

- ZoneFlowFertilizingIntervalSelect: "Next Fertilizing In" 1-12 months,
  paired with datetime.py's "Last Fertilizing" date -- the same kind of
  pure journal field as Health, with no effect on watering at all.

- ZoneFlowDemandModelSelect: which routine weekly-target model the zone
  uses -- the original temperature tiers (default) or the Hargreaves ET
  curve. Unlike the journal fields this one DOES change watering; see
  const.py's DEMAND_MODEL_* comment.

All of them persist through IrrigationState (state_store.py), the same Store
already used for the planting date etc., so a value set here survives an
HA restart exactly like everything else that store holds.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEMAND_MODEL_OPTIONS,
    DOMAIN,
    FERTILIZING_INTERVAL_OPTIONS,
    GROWTH_RAMP_PROFILE_OPTIONS,
    GROWTH_STAGE_MODE_AUTO,
    GROWTH_STAGE_PRESETS,
    GROWTH_STAGE_SELECT_OPTIONS,
    HEALTH_STATUS_OPTIONS,
    SOIL_TYPE_OPTIONS,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ZoneFlowSoilTypeSelect(entry, controller),
            ZoneFlowGrowthStageSelect(entry, controller),
            ZoneFlowGrowthRampProfileSelect(entry, controller),
            ZoneFlowHealthSelect(entry, controller),
            ZoneFlowFertilizingIntervalSelect(entry, controller),
            ZoneFlowDemandModelSelect(entry, controller),
        ]
    )


class _Base(SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, controller) -> None:
        self._controller = controller
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ZoneFlow",
        )


class ZoneFlowSoilTypeSelect(_Base):
    """Live override of the zone's soil type -- see module docstring.
    Selecting an option here takes effect immediately (no config-entry
    reload), and is exactly the same value ZoneFlowSoilProfileSensor
    (sensor.py) and every internal soil_type read return afterward."""

    _attr_icon = "mdi:layers-outline"
    _attr_options = SOIL_TYPE_OPTIONS
    _attr_translation_key = "soil_type"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_soil_type_select"

    @property
    def current_option(self) -> str:
        return self._controller.soil_type

    async def async_select_option(self, option: str) -> None:
        self._controller.store.state.soil_type_override = option
        await self._controller.store.async_save()
        self.async_write_ha_state()


class ZoneFlowGrowthStageSelect(_Base):
    """Manual growth-stage control -- see module docstring and const.py's
    GROWTH_STAGE_MODE_* comment. Picking a named preset also pushes that
    preset's percentage into the paired "Growth Stage Manual Override"
    number entity, so the slider and the dropdown always agree right after
    a preset is chosen; moving the slider afterward doesn't change the
    dropdown back (there is no single preset name for an arbitrary
    percentage) -- reselecting "Manual" is the honest way to represent
    "using the slider's current value" once it's been hand-tuned."""

    _attr_icon = "mdi:sprout-outline"
    _attr_options = GROWTH_STAGE_SELECT_OPTIONS
    _attr_translation_key = "growth_stage_mode"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_growth_stage_select"

    @property
    def current_option(self) -> str:
        return self._controller.store.state.growth_stage_mode

    async def async_select_option(self, option: str) -> None:
        state = self._controller.store.state
        if option == GROWTH_STAGE_MODE_AUTO:
            state.growth_stage_mode = GROWTH_STAGE_MODE_AUTO
        else:
            state.growth_stage_mode = "manual"
            preset_pct = GROWTH_STAGE_PRESETS.get(option)
            if preset_pct is not None:
                number_entity = self._controller.numbers.get("growth_stage_override_pct")
                if number_entity is not None:
                    await number_entity.async_set_native_value(preset_pct)
        await self._controller.store.async_save()
        self.async_write_ha_state()


class ZoneFlowGrowthRampProfileSelect(_Base):
    """Live override of which growth-ramp curve this zone follows -- see
    module docstring. Switching to "custom" doesn't populate the custom
    curve's sliders on its own (they keep whatever they were last set to,
    including their untouched defaults from const.py) -- set those
    separately on the zone's "Custom Ramp: ..." number entities."""

    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_options = GROWTH_RAMP_PROFILE_OPTIONS
    _attr_translation_key = "growth_ramp_profile"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_growth_ramp_profile_select"

    @property
    def current_option(self) -> str:
        return self._controller.growth_ramp_profile

    async def async_select_option(self, option: str) -> None:
        self._controller.store.state.growth_ramp_profile_override = option
        await self._controller.store.async_save()
        self.async_write_ha_state()


class ZoneFlowHealthSelect(_Base):
    """Pure human journal field -- see module docstring. Deliberately has
    no getter/setter into the controller's watering logic at all; this is
    the entire implementation, on purpose."""

    _attr_icon = "mdi:sprout"
    _attr_options = HEALTH_STATUS_OPTIONS
    _attr_translation_key = "health_status"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_health_status_select"

    @property
    def current_option(self) -> str:
        return self._controller.store.state.health_status

    async def async_select_option(self, option: str) -> None:
        self._controller.store.state.health_status = option
        await self._controller.store.async_save()
        self.async_write_ha_state()


class ZoneFlowFertilizingIntervalSelect(_Base):
    """Pure journal field -- how many months after the last feed (see
    datetime.py's "Last Fertilizing") the next one is planned. Same as
    ZoneFlowHealthSelect: nothing in the controller reads it."""

    _attr_icon = "mdi:calendar-refresh"
    _attr_options = FERTILIZING_INTERVAL_OPTIONS
    _attr_translation_key = "fertilizing_interval"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_fertilizing_interval_select"

    @property
    def current_option(self) -> str:
        return self._controller.store.state.fertilizing_interval_months

    async def async_select_option(self, option: str) -> None:
        self._controller.store.state.fertilizing_interval_months = option
        await self._controller.store.async_save()
        self.async_write_ha_state()


class ZoneFlowDemandModelSelect(_Base):
    """Routine weekly-target model -- see const.py's DEMAND_MODEL_* comment.
    Read by ZoneFlowController.et_weekly_target_mm() at each routine cycle,
    so a change applies from the next cycle with no reload."""

    _attr_icon = "mdi:chart-bell-curve"
    _attr_options = DEMAND_MODEL_OPTIONS
    _attr_translation_key = "demand_model"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_demand_model_select"

    @property
    def current_option(self) -> str:
        return self._controller.store.state.demand_model

    async def async_select_option(self, option: str) -> None:
        self._controller.store.state.demand_model = option
        await self._controller.store.async_save()
        self.async_write_ha_state()
