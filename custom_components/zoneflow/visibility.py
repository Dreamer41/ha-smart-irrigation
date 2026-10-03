"""Which of a zone's entities are hidden, so its device page and Home
Assistant's auto-generated dashboards only show what the zone uses.

Hidden, never removed: a hidden entity keeps working and keeps its value,
still shows on any card a person placed it on, and can be unhidden under the
entity's settings. ZoneFlow only hides or unhides an entity when the reason
changes (a feature switched on or off) -- never on every restart -- so an
entity a person unhid themselves stays visible, and one they hid
themselves is never touched (only hides made by the integration are
undone).
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import GREENHOUSE_NUMBERS, GROWTH_RAMP_CUSTOM, GROWTH_RAMP_OFF

# (platform, translation key) of each group, and when it has nothing to do.
FORECAST = {
    ("number", "forecast_rain_threshold_mm"),
    ("number", "forecast_probability_threshold_pct"),
    ("number", "forecast_dry_override_days"),
}
RAIN_GAUGE = {
    ("number", "rain_mm_per_tip"),
    ("number", "preirrigation_rain_threshold_mm"),
    ("number", "deep_soak_rain_threshold"),
    ("sensor", "rain_past_30min"),
    ("sensor", "rain_past_24h"),
    ("sensor", "rain_past_3d"),
    ("sensor", "rain_past_7d"),
    ("sensor", "rain_past_14d"),
    ("sensor", "rain_today"),
}
PUMP_POWER = {("number", "pump_min_watts")}
SHARED_PUMP = {("number", "pump_preamble_seconds"), ("number", "pump_postamble_seconds")}
TEMPERATURE = {
    ("sensor", "avg_peak_temp_3d"),
    ("sensor", "reference_et0_3d"),
    ("number", "crop_coefficient"),
    ("select", "demand_model"),
}
FROST = {("number", "frost_guard_temp")}
NOTIFY = {("select", "notifications"), ("select", "weekly_summary")}
FLOW_METER = {("sensor", "last_cycle_water_liters")}
DEEP_SOAK = {
    ("number", "deep_soak_target_mm"),
    ("number", "deep_soak_max_runtime_minutes"),
    ("number", "deep_soak_drydown_days"),
    ("number", "deep_soak_interval_days"),
    ("number", "deep_soak_rain_threshold"),
    ("number", "deep_soak_pulse_count"),
    ("number", "deep_soak_pulse_rest_minutes"),
    ("button", "run_deep_soak"),
}
CUSTOM_RAMP = {
    ("number", "growth_ramp_custom_start_pct"),
    ("number", "growth_ramp_custom_point1_day"),
    ("number", "growth_ramp_custom_point1_pct"),
    ("number", "growth_ramp_custom_point2_day"),
    ("number", "growth_ramp_custom_point2_pct"),
    ("number", "growth_ramp_custom_full_day"),
}
GROWTH_RAMP = {
    ("select", "growth_stage_mode"),
    ("number", "growth_stage_override_pct"),
    ("sensor", "growth_ramp_pct"),
}
# Fine-tuning almost nobody needs: hidden from the start, and (since the
# reason never changes) left as the person sets it after that.
ADVANCED = {
    ("number", "rain_eff_low"),
    ("number", "rain_eff_mid"),
    ("number", "rain_eff_high"),
}


# The greenhouse / indoor climate entities (1.6), each shown only when the
# hardware or sensor it acts on is configured.
_GH_NUMBERS = {("number", key) for key in GREENHOUSE_NUMBERS}
GH_ALWAYS = {("switch", "greenhouse_control"), ("sensor", "greenhouse_status")}
GH_HEAT = {("number", "heat_temp"), ("select", "heater_failsafe")}
GH_VENT = {("number", "vent_temp"), ("number", "vent_open_pct"), ("select", "ventilation_failsafe")}
GH_FAN = {("number", "fan_temp")}
GH_OUTSIDE = {("number", "outside_margin"), ("binary_sensor", "ventilation_allowed")}
GH_HUMIDITY = {("number", "max_humidity"), ("sensor", "inside_vpd")}
GH_MIST = {
    ("number", "mist_temp"), ("number", "mist_min_humidity"), ("number", "mist_stop_humidity"),
    ("number", "mist_min_temp"), ("number", "mist_light_level"), ("number", "mist_on_seconds"),
    ("number", "mist_off_seconds"), ("number", "max_mist_minutes_per_hour"),
    ("switch", "mist_at_night"), ("select", "misting_trigger"), ("sensor", "misting_today"),
}
GH_MIST_HUMIDITY = {("number", "mist_min_humidity"), ("number", "mist_stop_humidity")}
GH_LIGHT = {("number", "mist_light_level")}
GH_ANY_DEVICE = {("number", "climate_hysteresis"), ("number", "manual_hold_minutes")}
GH_ALL = _GH_NUMBERS | GH_ALWAYS | GH_HEAT | GH_VENT | GH_OUTSIDE | GH_HUMIDITY | GH_MIST

# What a zone without a valve still shows: its phone-message setting and the
# climate entities (the reset button too, when it has misters).
KEEP_WITHOUT_VALVE = {("select", "notifications")} | GH_ALL


def _greenhouse_hidden(controller) -> set[tuple[str, str]]:
    hidden: set[tuple[str, str]] = set()
    fans, vents = bool(controller.fan_entities), bool(controller.vent_entities)
    misters, heater = bool(controller.mister_entities), bool(controller.heater_entities)
    if not heater:
        hidden |= GH_HEAT
    if not vents:
        hidden |= GH_VENT
    if not fans:
        hidden |= GH_FAN
    if not (fans or vents) or not controller.outside_temp_entity:
        hidden |= GH_OUTSIDE
    if not controller.inside_humidity_entity:
        hidden |= GH_HUMIDITY | GH_MIST_HUMIDITY
    elif not (fans or vents):
        hidden.add(("number", "max_humidity"))
    if not misters:
        hidden |= GH_MIST
    if not controller.light_entity:
        hidden |= GH_LIGHT
    if not (fans or vents or misters or heater):
        hidden |= GH_ANY_DEVICE
    return hidden


def hidden_for(controller) -> set[tuple[str, str]]:
    """The entities that do nothing for this zone right now."""
    hidden = set(ADVANCED)
    if not controller.weather_entity:
        hidden |= FORECAST
    if not controller.rain_counter_entity:
        hidden |= RAIN_GAUGE
    if not controller.pump_power_entity:
        hidden |= PUMP_POWER
    if (
        not controller.pump_id
        and not controller.pump_power_entity  # the older "same pump-power sensor" grouping
        and not any(controller.number(key) for _domain, key in SHARED_PUMP)
    ):
        hidden |= SHARED_PUMP
    if not controller.outdoor_temp_entity:
        hidden |= TEMPERATURE
    if not controller.outdoor_temp_entity and not controller.weather_entity:
        hidden |= FROST  # nothing to read the temperature from
    if not controller.notify_entity:
        hidden |= NOTIFY
    if not controller.flow_meter_entity:
        hidden |= FLOW_METER
    if not controller.deep_soak_enabled:
        hidden |= DEEP_SOAK
    if not controller.is_outdoor:
        hidden |= _greenhouse_hidden(controller)
    profile = controller.growth_ramp_profile
    if profile == GROWTH_RAMP_OFF:
        hidden |= GROWTH_RAMP | CUSTOM_RAMP
    elif profile != GROWTH_RAMP_CUSTOM:
        hidden |= CUSTOM_RAMP
    return hidden


async def async_apply(hass: HomeAssistant, entry, controller) -> None:
    """Hide what just became irrelevant and unhide what just became relevant
    again -- only on a change, compared with what this zone hid last time."""
    wanted = hidden_for(controller)
    state = controller.store.state
    previous = {tuple(item) for item in state.auto_hidden}
    registry = er.async_get(hass)
    if not controller.has_valve:
        # A climate-only zone never waters: hide all the watering entities
        # (they come back by themselves if a valve is added later).
        wanted |= {
            (reg_entry.domain, reg_entry.translation_key)
            for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
            if reg_entry.translation_key
        } - KEEP_WITHOUT_VALVE
        if controller.mister_entities:
            wanted.discard(("button", "reset_lock"))
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = (reg_entry.domain, reg_entry.translation_key)
        if key in wanted and key not in previous and reg_entry.hidden_by is None:
            registry.async_update_entity(reg_entry.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION)
        elif key not in wanted and reg_entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
            # Only ZoneFlow sets this hider (a person's unhide clears it), so
            # this never touches a person's choice -- and it also recovers
            # an entity whose record was lost (e.g. after a downgrade).
            registry.async_update_entity(reg_entry.entity_id, hidden_by=None)
    new = sorted(list(key) for key in wanted)
    if new != sorted(list(key) for key in previous):
        state.auto_hidden = new
        await controller.store.async_save()
