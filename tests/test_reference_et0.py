"""Daily min/max temperature tracking + the display-only Reference ET0
sensor (Hargreaves-Samani, see calculations.py). Part 1 of the ET work:
nothing in the watering math reads ET0 yet, so these tests only cover the
tracking, the daily shift, and what the sensor reports.
"""
import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()


async def _setup(hass):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _et0_entity(hass):
    return next(s.entity_id for s in hass.states.async_all("sensor") if "reference_et" in s.entity_id)


@pytest.mark.asyncio
async def test_daily_min_and_max_track_every_reading(hass, fake_valve_services):
    await _seed(hass)
    controller = await _setup(hass)
    controller._start_new_day(seed_temp=28.0)

    for reading in ("26.5", "31.0", "24.8", "29.0"):
        hass.states.async_set(OUTDOOR_TEMP, reading)
        await hass.async_block_till_done()

    assert controller.store.state.today_min_temp_c == 24.8
    assert controller.store.state.today_peak_temp_c == 31.0


@pytest.mark.asyncio
async def test_daily_shift_records_the_min_alongside_the_peak(hass, fake_valve_services):
    await _seed(hass)
    controller = await _setup(hass)
    controller._start_new_day(seed_temp=25.0)
    hass.states.async_set(OUTDOOR_TEMP, "32.0")
    await hass.async_block_till_done()

    controller._on_daily_shift(None)
    await hass.async_block_till_done()

    assert controller.store.state.min_temp_day_history_c[0] == 25.0
    assert controller.store.state.peak_temp_day_history_c[0] == 32.0


@pytest.mark.asyncio
async def test_a_day_with_no_readings_shifts_in_none_not_a_fallback(hass, fake_valve_services):
    await _seed(hass)
    controller = await _setup(hass)
    controller._start_new_day(seed_temp=None)

    controller._on_daily_shift(None)
    await hass.async_block_till_done()

    assert controller.store.state.min_temp_day_history_c[0] is None
    # The peak register still carries its own fallback, as before -- but
    # with no paired minimum that day contributes nothing to ET0.
    assert controller.et0_daily_history()[0] is None


@pytest.mark.asyncio
async def test_first_partial_day_after_install_is_left_out(hass, fake_valve_services):
    """Upgrading mid-day: the peak has been tracked since midnight but the
    minimum hasn't, so today must not get recorded with a too-narrow range."""
    await _seed(hass)
    controller = await _setup(hass)
    controller.store.state.today_peak_temp_c = 31.0
    controller.store.state.today_min_temp_c = None

    hass.states.async_set(OUTDOOR_TEMP, "29.0")
    await hass.async_block_till_done()
    assert controller.store.state.today_min_temp_c is None

    controller._on_daily_shift(None)
    await hass.async_block_till_done()
    assert controller.store.state.min_temp_day_history_c[0] is None


@pytest.mark.asyncio
async def test_et0_sensor_is_unknown_until_a_full_day_is_recorded(hass, fake_valve_services):
    await _seed(hass)
    await _setup(hass)
    state = hass.states.get(_et0_entity(hass))
    assert state.state == "unknown"
    assert state.attributes["unit_of_measurement"] == "mm/d"
    assert state.attributes["method"].startswith("Hargreaves")


@pytest.mark.asyncio
async def test_et0_sensor_averages_the_recorded_days_at_the_home_latitude(hass, fake_valve_services):
    await _seed(hass)
    await hass.config.async_update(latitude=9.5)
    controller = await _setup(hass)
    controller.store.state.min_temp_day_history_c = [25.0, 24.0, None]
    controller.store.state.peak_temp_day_history_c = [32.0, 33.0, 30.0]

    daily = controller.et0_daily_history()
    assert daily[2] is None
    assert daily[0] is not None and daily[1] is not None
    assert controller.avg_et0() == calc.average_et0(daily)
    assert 4.0 < controller.avg_et0() < 6.0

    entity_id = _et0_entity(hass)
    ent = next(e for e in hass.data["sensor"].entities if e.entity_id == entity_id)
    ent.async_write_ha_state()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(controller.avg_et0())
    assert state.attributes["latitude"] == 9.5


@pytest.mark.asyncio
async def test_et0_does_not_change_the_routine_watering_target(hass, fake_valve_services):
    """Part 1 is display-only: recording ET0-relevant history must not move
    the weekly target the routine cycle actually uses."""
    await _seed(hass)
    controller = await _setup(hass)
    before = controller.effective_avg_peak_temp()
    controller.store.state.min_temp_day_history_c = [18.0, 18.0, 18.0]
    assert controller.effective_avg_peak_temp() == before
