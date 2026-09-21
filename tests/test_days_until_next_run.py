"""ZoneFlowDaysUntilNextRunSensor: the same next-irrigation estimate as
ZoneFlowNextIrrigationSensor, expressed as a days-remaining countdown
instead of a calendar timestamp -- see sensor.py's ZoneFlowDaysUntilNextRunSensor
docstring for why negative countdowns are clamped to 0 rather than shown.

Reads native_value directly off the sensor object (like
test_sensor_dropouts.py reads controller.rain_windows() directly) rather
than through hass.states.get(), since these are should_poll=True sensors
and a direct controller.store.state mutation doesn't trigger an immediate
re-poll of the already-registered entity.
"""
import pytest
import homeassistant.util.dt as dt_util

from custom_components.zoneflow.const import DOMAIN
from custom_components.zoneflow.sensor import ZoneFlowDaysUntilNextRunSensor

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "0")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_days_until_next_run_is_none_before_any_run(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    sensor = ZoneFlowDaysUntilNextRunSensor(entry, controller)
    assert sensor.native_value is None


@pytest.mark.asyncio
async def test_days_until_next_run_matches_the_routine_interval(hass, fake_valve_services):
    """Just watered, no temp history (falls back to the normal/4-day tier,
    see avg_peak_temp()'s 30.0 fallback vs. the default 31.5 hot threshold)
    -- next run should be ~4 days out, matching routine_drydown_days'
    default of 4.0."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    now_ts = dt_util.utcnow().timestamp()
    controller.store.state.last_routine_ts = now_ts
    controller.store.state.last_significant_rain_ts = 0.0

    sensor = ZoneFlowDaysUntilNextRunSensor(entry, controller)
    assert 3.9 <= sensor.native_value <= 4.1


@pytest.mark.asyncio
async def test_days_until_next_run_clamps_to_zero_when_overdue(hass, fake_valve_services):
    """An estimate that's already in the past (e.g. still waiting on the
    rain-credit calc to actually fire the gate) must read as "0 days" --
    due now -- never a negative countdown, which would just look broken
    on a dashboard or cheat sheet."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    ten_days_ago = dt_util.utcnow().timestamp() - 10 * 86400
    controller.store.state.last_routine_ts = ten_days_ago
    controller.store.state.last_significant_rain_ts = ten_days_ago

    sensor = ZoneFlowDaysUntilNextRunSensor(entry, controller)
    assert sensor.native_value == 0.0
