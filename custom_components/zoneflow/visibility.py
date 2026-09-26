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

from .const import GROWTH_RAMP_CUSTOM, GROWTH_RAMP_OFF

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
