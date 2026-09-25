"""Temperature unit handling: ZoneFlow works in degC internally, but Home
Assistant reports a temperature sensor in the instance's own unit system.
A Fahrenheit reading must be converted, not taken as degC (89.6F used to be
recorded as an 89.6C peak, which the 15-50C sanity range then threw away,
silently pinning the zone to the normal tier).
"""
import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _setup(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "80.0", {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    controller._start_new_day(seed_temp=None)
    return controller


@pytest.mark.asyncio
async def test_fahrenheit_readings_are_tracked_in_celsius(hass, fake_valve_services):
    controller = await _setup(hass)
    for reading in ("77.0", "89.6"):
        hass.states.async_set(OUTDOOR_TEMP, reading, {"unit_of_measurement": "°F"})
        await hass.async_block_till_done()

    assert controller.store.state.today_min_temp_c == pytest.approx(25.0)
    assert controller.store.state.today_peak_temp_c == pytest.approx(32.0)


@pytest.mark.asyncio
async def test_a_hot_fahrenheit_day_reaches_the_hot_tier(hass, fake_valve_services):
    controller = await _setup(hass)
    hass.states.async_set(OUTDOOR_TEMP, "95.0", {"unit_of_measurement": "°F"})  # 35C
    await hass.async_block_till_done()
    controller._on_daily_shift(None)
    await hass.async_block_till_done()

    assert controller.store.state.peak_temp_day_history_c[0] == pytest.approx(35.0)
    assert controller.avg_peak_temp() >= controller.number("hot_temp_threshold")


@pytest.mark.asyncio
async def test_celsius_and_unitless_readings_are_unchanged(hass, fake_valve_services):
    controller = await _setup(hass)
    hass.states.async_set(OUTDOOR_TEMP, "31.0", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    hass.states.async_set(OUTDOOR_TEMP, "27.0")
    await hass.async_block_till_done()

    assert controller.store.state.today_peak_temp_c == 31.0
    assert controller.store.state.today_min_temp_c == 27.0


@pytest.mark.asyncio
async def test_midnight_seed_is_converted_too(hass, fake_valve_services):
    controller = await _setup(hass)
    hass.states.async_set(OUTDOOR_TEMP, "77.0", {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()
    controller._on_midnight(None)
    await hass.async_block_till_done()

    assert controller.store.state.today_peak_temp_c == pytest.approx(25.0)
    assert controller.store.state.today_min_temp_c == pytest.approx(25.0)
