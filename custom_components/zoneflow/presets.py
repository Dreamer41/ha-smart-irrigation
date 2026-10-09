"""Copy settings and saved presets (1.7.0).

A *bundle* is a zone's watering settings, without anything that belongs to its
hardware or to the individual plant: no valve, pump, sensors, flow rate,
rain gauge tip size, planting date or health notes. A new zone can start from
another zone's bundle, an existing zone can take one, and a bundle can be
saved under a name (a preset) for later.

A bundle is {"numbers": {...}, "state": {...}, "options": {...}}: sliders (in
metric), settings kept in the zone's saved state, and settings kept in the
zone's config entry.
"""
from __future__ import annotations

import uuid
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .const import (
    CONF_DEEP_SOAK_ENABLED,
    CONF_DEEP_SOAK_SUN_MODE,
    CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_TIME,
    CONF_DRAINAGE,
    CONF_GROWTH_RAMP_PROFILE,
    CONF_IRRIGATION_METHOD,
    CONF_ROUTINE_SUN_MODE,
    CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_ROUTINE_TIME,
    CONF_SLOPE,
    CONF_SOIL_TYPE,
    DOMAIN,
)

PRESET_BOOK_KEY = "zoneflow_preset_book"
NAME_MAX_LENGTH = 40

COPY_NUMBER_KEYS = (
    "target_weekly_mm", "target_weekly_hot_mm", "target_weekly_cool_mm", "crop_coefficient",
    "hot_temp_threshold", "cool_temp_threshold", "frost_guard_temp",
    "rain_eff_low", "rain_eff_mid", "rain_eff_high",
    "deep_soak_target_mm", "deep_soak_max_runtime_minutes", "deep_soak_drydown_days",
    "deep_soak_interval_days", "deep_soak_rain_threshold",
    "max_runtime_minutes", "max_daily_runtime_minutes", "routine_drydown_days",
    "preirrigation_rain_threshold_mm",
    "forecast_rain_threshold_mm", "forecast_probability_threshold_pct", "forecast_dry_override_days",
    "deficit_water_pct", "mulch_et_adjustment_pct",
    "routine_pulse_count", "routine_pulse_rest_minutes", "deep_soak_pulse_count", "deep_soak_pulse_rest_minutes",
    "growth_stage_override_pct",
    "growth_ramp_custom_start_pct", "growth_ramp_custom_point1_day", "growth_ramp_custom_point1_pct",
    "growth_ramp_custom_point2_day", "growth_ramp_custom_point2_pct", "growth_ramp_custom_full_day",
)
# Kept in the zone's saved state.
COPY_STATE_KEYS = (
    "growth_stage_mode", "demand_model", "mulch_status", "notify_level", "fertilizing_interval_months",
    "soil_type_override", "drainage_override", "slope_override", "growth_ramp_profile_override",
)
# Kept in the zone's config entry (and asked for at setup under these names).
COPY_OPTION_KEYS = (
    CONF_ROUTINE_TIME, CONF_DEEP_SOAK_TIME,
    CONF_ROUTINE_SUN_MODE, CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_SUN_MODE, CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_ENABLED, CONF_IRRIGATION_METHOD,
    CONF_SOIL_TYPE, CONF_DRAINAGE, CONF_SLOPE, CONF_GROWTH_RAMP_PROFILE,
)


def capture(controller: Any) -> dict[str, Any]:
    """The zone's settings as a bundle."""
    entry = controller.entry
    state = controller.store.state
    numbers = {key: float(controller.number(key)) for key in COPY_NUMBER_KEYS if key in controller.numbers}
    values = {key: getattr(state, key, None) for key in COPY_STATE_KEYS}
    # What the zone is using now, whether it came from the setup or a dropdown.
    values["soil_type_override"] = controller.soil_type
    values["drainage_override"] = controller.drainage
    values["slope_override"] = controller.slope
    values["growth_ramp_profile_override"] = controller.growth_ramp_profile
    options = {}
    for key in COPY_OPTION_KEYS:
        found = entry.options.get(key, entry.data.get(key))
        if found is not None:
            options[key] = found
    options[CONF_DEEP_SOAK_ENABLED] = bool(controller.deep_soak_enabled)
    options[CONF_SOIL_TYPE] = controller.soil_type
    options[CONF_DRAINAGE] = controller.drainage
    options[CONF_SLOPE] = controller.slope
    options[CONF_GROWTH_RAMP_PROFILE] = controller.growth_ramp_profile
    return {"numbers": numbers, "state": {k: v for k, v in values.items() if v is not None}, "options": options}


async def async_apply(hass: HomeAssistant, controller: Any, bundle: dict[str, Any]) -> None:
    """Put a bundle on an existing zone."""
    for key, value in (bundle.get("numbers") or {}).items():
        entity = controller.numbers.get(key)
        if entity is not None and value is not None:
            await entity.async_set_metric_value(float(value))
    state = controller.store.state
    for key, value in (bundle.get("state") or {}).items():
        if key in COPY_STATE_KEYS and hasattr(state, key):
            setattr(state, key, value)
    await controller.store.async_save()
    if controller.plants is not None:
        controller.plants._last = controller.plants.values()  # not logged as edits of the plant
    controller._notify_status()
    # Settings kept in the zone's config entry restart the zone when they change.
    wanted = {k: v for k, v in (bundle.get("options") or {}).items() if k in COPY_OPTION_KEYS}
    entry = controller.entry
    current = {**entry.data, **entry.options}
    if any(current.get(k) != v for k, v in wanted.items()):
        hass.config_entries.async_update_entry(entry, options={**entry.options, **wanted})


class PresetBook:
    """The saved presets, in one store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, 1, f"{DOMAIN}_presets")
        self.presets: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        raw = await self._store.async_load()
        if isinstance(raw, dict) and isinstance(raw.get("presets"), dict):
            self.presets = raw["presets"]

    async def _save(self) -> None:
        await self._store.async_save({"presets": self.presets})

    def named(self, name: str) -> dict[str, Any] | None:
        return next((p for p in self.presets.values() if p["name"].casefold() == name.casefold()), None)

    def listing(self) -> list[dict[str, Any]]:
        return sorted(self.presets.values(), key=lambda p: p["name"].casefold())

    async def async_save_preset(self, name: str, bundle: dict[str, Any]) -> dict[str, Any]:
        """Save under a name; the same name (any letter case) replaces it."""
        existing = self.named(name)
        preset = existing or {"id": uuid.uuid4().hex, "name": name, "created_ts": dt_util.utcnow().timestamp()}
        preset["name"] = name
        preset["bundle"] = bundle
        preset["saved_ts"] = dt_util.utcnow().timestamp()
        self.presets[preset["id"]] = preset
        await self._save()
        return preset

    async def async_delete(self, preset_id: str) -> bool:
        if self.presets.pop(preset_id, None) is None:
            return False
        await self._save()
        return True


async def async_get_book(hass: HomeAssistant) -> PresetBook:
    book = hass.data.get(PRESET_BOOK_KEY)
    if book is None:
        book = PresetBook(hass)
        hass.data[PRESET_BOOK_KEY] = book
        await book.async_load()
    return book


def clean_name(value: Any) -> str:
    return " ".join(str(value or "").split())[:NAME_MAX_LENGTH]


# --- what a person can do ------------------------------------------------------


def _error(key: str, **placeholders: Any):
    from homeassistant.exceptions import ServiceValidationError

    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders or None)


async def save_preset(hass: HomeAssistant, controller: Any, name: str) -> dict[str, Any]:
    """Save a zone's settings under a name (the same name replaces)."""
    name = clean_name(name)
    if not name:
        raise _error("preset_name_required")
    return await (await async_get_book(hass)).async_save_preset(name, capture(controller))


async def delete_preset(hass: HomeAssistant, name: str) -> None:
    book = await async_get_book(hass)
    preset = book.named(clean_name(name))
    if preset is None:
        raise _error("preset_not_found")
    await book.async_delete(preset["id"])


async def copy_settings(hass: HomeAssistant, target: Any, source: Any = None, preset_name: str | None = None) -> None:
    """Give a zone another zone's settings, or a saved preset's."""
    if preset_name:
        preset = (await async_get_book(hass)).named(clean_name(preset_name))
        if preset is None:
            raise _error("preset_not_found")
        bundle, label = preset["bundle"], preset["name"]
    elif source is not None:
        if source is target:
            raise _error("copy_same_zone")
        bundle, label = capture(source), source.entry.title
    else:
        raise _error("copy_source_required")
    await async_apply(hass, target, bundle)
    from .plants import async_get_book as plant_book

    plants = await plant_book(hass)
    main = plants.main(target.entry.entry_id)
    if main is not None:
        plants.add_history(main["id"], "copied", source=label)
