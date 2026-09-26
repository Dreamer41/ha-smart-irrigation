"""1.5.0 batch 1: entity categories, hiding what a zone doesn't use, and the
diagnostics download.

Hidden, never removed: a hidden entity keeps working and keeps its value,
and ZoneFlow only hides/unhides when the reason changes -- a person's own
choice (unhiding something, or hiding it themselves) is left alone.
"""
from __future__ import annotations

import pytest
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from custom_components.zoneflow.const import (
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

HIDDEN_BY_ZONEFLOW = er.RegistryEntryHider.INTEGRATION


async def _setup(hass, **overrides):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()
    entry = make_entry(hass, **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]


def _reg(hass, entry, domain, key):
    registry = er.async_get(hass)
    return next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == domain and e.translation_key == key
    )


def _hidden(hass, entry, domain, key):
    return _reg(hass, entry, domain, key).hidden_by


async def _set_options(hass, entry, **options):
    hass.config_entries.async_update_entry(entry, options={**entry.options, **options})
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_entity_categories(hass, fake_valve_services):
    entry, _ = await _setup(hass)
    cat = lambda d, k: _reg(hass, entry, d, k).entity_category  # noqa: E731
    assert cat("number", "target_weekly_mm") == EntityCategory.CONFIG
    assert cat("select", "soil_type") == EntityCategory.CONFIG
    assert cat("switch", "deep_soak_enabled") == EntityCategory.CONFIG
    assert cat("datetime", "last_routine") == EntityCategory.CONFIG
    assert cat("binary_sensor", "irrigation_in_progress") == EntityCategory.DIAGNOSTIC
    assert cat("sensor", "rain_past_24h") == EntityCategory.DIAGNOSTIC
    assert cat("sensor", "soil_profile") == EntityCategory.DIAGNOSTIC
    # Everyday entities stay in the main list.
    for domain, key in [
        ("sensor", "next_irrigation_estimate"),
        ("sensor", "days_until_next_run"),
        ("sensor", "rain_today"),
        ("switch", "deficit_mode"),
        ("switch", "service_mode"),
        ("button", "run_routine"),
        ("select", "health_status"),
        ("datetime", "last_fertilizing"),
    ]:
        assert cat(domain, key) is None, (domain, key)


@pytest.mark.asyncio
async def test_a_valve_only_zone_hides_everything_it_cannot_use(hass, fake_valve_services):
    entry, controller = await _setup(
        hass,
        **{CONF_PUMP_POWER_ENTITY: None, CONF_RAIN_COUNTER_ENTITY: None, CONF_OUTDOOR_TEMP_ENTITY: None},
    )
    for domain, key in [
        ("number", "forecast_rain_threshold_mm"),  # no weather entity
        ("number", "rain_mm_per_tip"),  # no rain gauge
        ("sensor", "rain_past_24h"),
        ("sensor", "rain_today"),
        ("number", "pump_min_watts"),  # no pump power sensor
        ("number", "pump_preamble_seconds"),  # no shared pump
        ("sensor", "avg_peak_temp_3d"),  # no temperature sensor
        ("select", "demand_model"),
        ("sensor", "last_cycle_water_liters"),  # no flow meter
        ("number", "growth_ramp_custom_start_pct"),  # growth ramp off
        ("select", "growth_stage_mode"),
        ("number", "rain_eff_mid"),  # advanced
    ]:
        assert _hidden(hass, entry, domain, key) == HIDDEN_BY_ZONEFLOW, (domain, key)
    for domain, key in [
        ("number", "target_weekly_mm"),
        ("number", "flow_rate_mm_per_min"),
        ("number", "fallback_temp"),  # the manual temperature for a zone without a sensor
        ("button", "run_routine"),
        ("button", "run_deep_soak"),  # deep soak is on
        ("sensor", "next_irrigation_estimate"),
    ]:
        assert _hidden(hass, entry, domain, key) is None, (domain, key)
    # Hidden still works, with its value.
    assert controller.number("forecast_rain_threshold_mm") == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_features_that_are_set_up_stay_visible(hass, fake_valve_services):
    entry, _ = await _setup(hass)  # pump power, rain gauge and temperature configured
    for domain, key in [
        ("number", "rain_mm_per_tip"),
        ("sensor", "rain_past_24h"),
        ("number", "pump_min_watts"),
        ("sensor", "avg_peak_temp_3d"),
        ("select", "demand_model"),
    ]:
        assert _hidden(hass, entry, domain, key) is None, (domain, key)
    assert _hidden(hass, entry, "number", "forecast_rain_threshold_mm") == HIDDEN_BY_ZONEFLOW


@pytest.mark.asyncio
async def test_adding_and_removing_a_feature_unhides_and_hides_again(hass, fake_valve_services):
    entry, _ = await _setup(hass)
    assert _hidden(hass, entry, "number", "forecast_dry_override_days") == HIDDEN_BY_ZONEFLOW
    await _set_options(hass, entry, **{CONF_WEATHER_ENTITY: "weather.home"})
    assert _hidden(hass, entry, "number", "forecast_dry_override_days") is None
    await _set_options(hass, entry, **{CONF_WEATHER_ENTITY: None})
    assert _hidden(hass, entry, "number", "forecast_dry_override_days") == HIDDEN_BY_ZONEFLOW


@pytest.mark.asyncio
async def test_a_persons_own_choice_is_left_alone(hass, fake_valve_services):
    entry, _ = await _setup(hass)
    registry = er.async_get(hass)
    # Unhid an advanced slider themselves: it stays visible after a reload.
    eff = _reg(hass, entry, "number", "rain_eff_low").entity_id
    registry.async_update_entity(eff, hidden_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _hidden(hass, entry, "number", "rain_eff_low") is None

    # Hid something themselves: ZoneFlow never unhides it.
    await _set_options(hass, entry, **{CONF_WEATHER_ENTITY: "weather.home"})
    prob = _reg(hass, entry, "number", "forecast_probability_threshold_pct").entity_id
    registry.async_update_entity(prob, hidden_by=er.RegistryEntryHider.USER)
    await _set_options(hass, entry, **{CONF_WEATHER_ENTITY: None})
    await _set_options(hass, entry, **{CONF_WEATHER_ENTITY: "weather.home"})
    assert _hidden(hass, entry, "number", "forecast_probability_threshold_pct") == er.RegistryEntryHider.USER


@pytest.mark.asyncio
async def test_growth_ramp_profile_shows_its_own_settings_without_a_reload(hass, fake_valve_services):
    entry, controller = await _setup(hass)
    profile_select = _reg(hass, entry, "select", "growth_ramp_profile").entity_id
    assert _hidden(hass, entry, "number", "growth_ramp_custom_full_day") == HIDDEN_BY_ZONEFLOW

    await hass.services.async_call("select", "select_option", {"entity_id": profile_select, "option": "custom"}, blocking=True)
    assert hass.data[DOMAIN][entry.entry_id] is controller  # no reload
    assert _hidden(hass, entry, "number", "growth_ramp_custom_full_day") is None
    assert _hidden(hass, entry, "select", "growth_stage_mode") is None

    await hass.services.async_call(
        "select", "select_option", {"entity_id": profile_select, "option": "fast_annual"}, blocking=True
    )
    assert _hidden(hass, entry, "number", "growth_ramp_custom_full_day") == HIDDEN_BY_ZONEFLOW
    assert _hidden(hass, entry, "select", "growth_stage_mode") is None


@pytest.mark.asyncio
async def test_deep_soak_off_hides_its_settings_and_keeps_their_values(hass, fake_valve_services):
    entry, controller = await _setup(hass)
    await controller.numbers["deep_soak_target_mm"].async_set_native_value(33.0)
    switch = _reg(hass, entry, "switch", "deep_soak_enabled").entity_id
    from homeassistant.helpers.entity_component import DATA_INSTANCES

    await hass.data[DATA_INSTANCES]["switch"].get_entity(switch).async_turn_off()
    await hass.async_block_till_done()
    assert _hidden(hass, entry, "number", "deep_soak_target_mm") == HIDDEN_BY_ZONEFLOW
    assert _hidden(hass, entry, "button", "run_deep_soak") == HIDDEN_BY_ZONEFLOW

    await hass.data[DATA_INSTANCES]["switch"].get_entity(switch).async_turn_on()
    await hass.async_block_till_done()
    assert _hidden(hass, entry, "number", "deep_soak_target_mm") is None
    assert hass.data[DOMAIN][entry.entry_id].number("deep_soak_target_mm") == pytest.approx(33.0)


@pytest.mark.asyncio
async def test_diagnostics_download(hass, fake_valve_services):
    from custom_components.zoneflow.diagnostics import async_get_config_entry_diagnostics

    entry, _ = await _setup(hass, **{CONF_NOTIFY_ENTITY: "notify.mobile_app_juhas_phone"})
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"][CONF_NOTIFY_ENTITY] == "**REDACTED**"
    assert diag["version"]
    assert "target_weekly_mm" in diag["numbers"]
    assert set(diag["decisions_now"]) >= {"watering_temperature_c", "next_routine", "deficit_reason"}
    assert "rain_samples" not in diag["state"] and "rain_samples_summary" in diag["state"]
    assert any(e["key"] == "target_weekly_mm" for e in diag["entities"])
    import json

    json.dumps(diag)  # must be serialisable for the download


@pytest.mark.asyncio
async def test_pump_delays_stay_visible_for_zones_sharing_a_pump_power_sensor(hass, fake_valve_services):
    """Regression (review): zones on the same pump-power sensor share a pump
    (the older grouping) even without a pump ID -- their delays matter."""
    entry, _ = await _setup(hass)  # pump power sensor configured, no pump ID
    assert _hidden(hass, entry, "number", "pump_preamble_seconds") is None
    # A delay someone already set also keeps them visible.
    entry2, c2 = await _setup(hass, **{CONF_PUMP_POWER_ENTITY: None, "zone_name": "Other", "csv_path": "/tmp/other.csv"})
    assert _hidden(hass, entry2, "number", "pump_postamble_seconds") == HIDDEN_BY_ZONEFLOW
    await c2.numbers["pump_postamble_seconds"].async_set_native_value(5)
    assert await hass.config_entries.async_reload(entry2.entry_id)
    await hass.async_block_till_done()
    assert _hidden(hass, entry2, "number", "pump_postamble_seconds") is None


@pytest.mark.asyncio
async def test_a_lost_record_does_not_leave_entities_stuck_hidden(hass, fake_valve_services):
    """Regression (review): after a downgrade the saved list of what ZoneFlow
    hid is gone -- setting the feature up must still unhide its entities."""
    entry, controller = await _setup(hass)
    assert _hidden(hass, entry, "number", "forecast_dry_override_days") == HIDDEN_BY_ZONEFLOW
    controller.store.state.auto_hidden = []
    await controller.store.async_save()
    await _set_options(hass, entry, **{CONF_WEATHER_ENTITY: "weather.home"})
    assert _hidden(hass, entry, "number", "forecast_dry_override_days") is None


@pytest.mark.asyncio
async def test_diagnostics_show_real_slider_values_and_work_unloaded(hass, fake_valve_services):
    from custom_components.zoneflow.diagnostics import async_get_config_entry_diagnostics

    entry, controller = await _setup(hass)
    controller.store.state.health_notes = "Mum's chilis by the fence"
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["state"]["health_notes"] == "**REDACTED**"
    assert diag["numbers"]["fallback_temp"] == controller.numbers["fallback_temp"].metric_value

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "entities" in diag and "numbers" not in diag
