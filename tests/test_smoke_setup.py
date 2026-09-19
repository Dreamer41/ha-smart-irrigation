"""First smoke test: does the integration actually load in a real HA core
instance and create the entities it's supposed to? This is the check that
pure unit tests (test_calculations.py, test_rain_tracker.py) can't do --
it exercises the real config_flow-created entry, the real entity platforms,
RestoreNumber, and the service registry.
"""
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zoneflow.const import (
    CONF_CSV_PATH,
    CONF_DEEP_SOAK_TIME,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_TIME,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    DOMAIN,
)

VALVE = "switch.watering1"
PUMP = "sensor.waterpump_power_power"
RAIN_COUNTER = "sensor.rain_gauge_tips"
OUTDOOR_TEMP = "sensor.outdoor_temp_temperature"


def make_entry(hass, **overrides):
    data = {
        CONF_ZONE_NAME: "Test Zone",
        CONF_VALVE_ENTITY: VALVE,
        CONF_PUMP_POWER_ENTITY: PUMP,
        CONF_RAIN_COUNTER_ENTITY: RAIN_COUNTER,
        CONF_OUTDOOR_TEMP_ENTITY: OUTDOOR_TEMP,
        CONF_NOTIFY_ENTITY: None,
        CONF_CSV_PATH: "/tmp/test_zoneflow.csv",
        CONF_DEEP_SOAK_TIME: "05:00:00",
        CONF_ROUTINE_TIME: "05:30:00",
    }
    data.update(overrides)
    entry = MockConfigEntry(domain=DOMAIN, data=data, title=data[CONF_ZONE_NAME])
    entry.add_to_hass(hass)
    return entry


async def _seed_source_entities(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "0")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "30.0")
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_setup_creates_all_expected_entities(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # every tunable number entity
    from custom_components.zoneflow.const import NUMBER_DEFS

    for key, (name, *_rest) in NUMBER_DEFS.items():
        entity_id = None
        for state in hass.states.async_all("number"):
            if state.attributes.get("friendly_name", "").endswith(name):
                entity_id = state.entity_id
                break
        assert entity_id is not None, f"number entity for {key} ({name}) was not created"

    # diagnostic sensors
    sensor_ids = {s.entity_id for s in hass.states.async_all("sensor")}
    assert any("rain_past_24h" in e for e in sensor_ids)
    assert any("next_irrigation_estimate" in e for e in sensor_ids)
    assert any("3_day_average_peak_temperature" in e for e in sensor_ids)
    # Regression: a zone that has never run yet used to fall back to epoch
    # (Jan 1970) as its "last routine run" baseline, showing a nonsensical
    # "56 years ago" next-irrigation estimate in the UI. It should report
    # "unknown" instead until there's a real run to estimate from.
    next_irrigation_entity_id = next(e for e in sensor_ids if "next_irrigation_estimate" in e)
    assert hass.states.get(next_irrigation_entity_id).state == "unknown"

    # binary sensors
    binary_ids = {s.entity_id for s in hass.states.async_all("binary_sensor")}
    assert any("irrigation_in_progress" in e for e in binary_ids)
    assert any("irrigation_abort" in e for e in binary_ids)

    # switch (deep-soak on/off dashboard toggle -- see switch.py)
    switch_ids = {s.entity_id for s in hass.states.async_all("switch")}
    assert any("deep_soak_enabled" in e for e in switch_ids)

    # buttons
    button_ids = {s.entity_id for s in hass.states.async_all("button")}
    assert any("deep_soak" in e for e in button_ids)
    assert any("routine" in e for e in button_ids)
    assert any("reset" in e and "lock" in e for e in button_ids)

    # services
    assert hass.services.has_service(DOMAIN, "run_deep_soak")
    assert hass.services.has_service(DOMAIN, "run_routine_irrigation")
    assert hass.services.has_service(DOMAIN, "reset_lock")
    assert hass.services.has_service(DOMAIN, "test_pulse")

    # lock/abort start False, don't fire on setup alone
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.store.state.lock_on is False
    assert controller.store.state.abort_on is False
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_unload_cleans_up_services(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, "run_deep_soak")
