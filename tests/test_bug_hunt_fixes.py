"""1.8: findings of the outside bug hunt: implausible readings, a save that never happens, a valve
that is slow to close, the stuck-valve clock."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.core import State

from custom_components.zoneflow.const import DOMAIN
from custom_components.zoneflow.controller import ZoneFlowController as Z

from .test_smoke_setup import VALVE, _seed_source_entities, make_entry


async def _zone(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("t_min,t_max", [(60.0, 95.0), (12.0, 85.0), (float("nan"), 20.0), (-90.0, 10.0)])
async def test_an_impossible_temperature_gives_no_et0_for_the_day(hass, t_min, t_max):
    c = await _zone(hass)
    s = c.store.state
    s.today_min_temp_c, s.today_peak_temp_c = t_min, t_max
    c._close_et0_day(dt_util.now().date() - timedelta(days=1), dt_util.utcnow().timestamp())
    assert s.et0_day_history[0]["et0"] is None


def test_a_wind_sentinel_is_not_wind():
    for value in ("6553.5", "655.35", "inf", "-1"):
        assert Z._et0_reading("wind", State("sensor.w", value, {"unit_of_measurement": "m/s"})) is None
    assert Z._et0_reading("weather_wind", State("weather.h", "sunny", {"wind_speed": 6553, "wind_speed_unit": "km/h"})) is None
    assert Z._et0_reading("wind", State("sensor.w", "12", {"unit_of_measurement": "m/s"})) == 12.0


@pytest.mark.asyncio
async def test_a_sensor_that_reports_every_few_seconds_still_gets_saved(hass, monkeypatch):
    c = await _zone(hass)
    store = c.store
    store._save_asked_at = None
    calls = []
    monkeypatch.setattr(store._store, "async_delay_save", lambda fn, delay: calls.append((fn, delay)))
    for _ in range(500):
        store.schedule_save()
    assert len(calls) == 1  # asked once: Home Assistant would have pushed the deadline back each time
    calls[0][0]()  # the write happens and clears the flag
    store.schedule_save()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_a_valve_that_takes_a_while_to_close_is_waited_for(hass):
    c = await _zone(hass)
    hass.states.async_set(VALVE, "closing")
    hass.loop.call_later(1.2, lambda: hass.states.async_set(VALVE, "closed"))
    assert await c._valve_confirmed_closed(VALVE, seconds=0.5) is True
    hass.states.async_set(VALVE, "open")
    assert await c._valve_confirmed_closed(VALVE, seconds=0.5) is False
    hass.states.async_set(VALVE, "unavailable")
    assert await c._valve_confirmed_closed(VALVE, seconds=0.5) is False


@pytest.mark.asyncio
async def test_the_stuck_valve_clock_runs_from_the_first_opening(hass):
    c = await _zone(hass)
    hass.states.async_set(VALVE, "off")
    await hass.async_block_till_done()
    hass.states.async_set(VALVE, "opening")
    await hass.async_block_till_done()
    first = c._valve_open_since
    assert first is not None
    await asyncio.sleep(0.05)
    for state in ("open", "closing", "open"):
        hass.states.async_set(VALVE, state)
        await hass.async_block_till_done()
        assert c._valve_open_since == first
    hass.states.async_set(VALVE, "closed")
    await hass.async_block_till_done()
    assert c._valve_open_since is None


@pytest.mark.asyncio
async def test_a_closing_valve_does_not_fire_the_stuck_watchdog_again(hass):
    c = await _zone(hass)
    fired = []
    c._fire_valve_stuck = lambda: fired.append(1) or asyncio.sleep(0)
    hass.states.async_set(VALVE, "open")
    await hass.async_block_till_done()
    assert c._valve_stuck_cancel is not None
    armed = c._valve_stuck_cancel
    hass.states.async_set(VALVE, "closing")  # a normal close
    await hass.async_block_till_done()
    assert c._valve_stuck_cancel is armed  # the clock was not re-armed
    armed()  # (the real timer is replaced by firing it by hand)
    c._on_valve_stuck(dt_util.utcnow())  # it fires once
    await hass.async_block_till_done()
    hass.states.async_set(VALVE, "open")
    hass.states.async_set(VALVE, "closing")  # the close it sent: must not arm a second firing
    await hass.async_block_till_done()
    assert c._valve_stuck_cancel is None and len(fired) == 1
    hass.states.async_set(VALVE, "closed")
    await hass.async_block_till_done()
    assert c._valve_stuck_fired is False


@pytest.mark.asyncio
async def test_a_climate_reading_does_not_write_the_whole_state(hass, monkeypatch):
    from custom_components.zoneflow.const import CONF_HUMIDITY_ENTITY

    await _seed_source_entities(hass)
    hass.states.async_set("sensor.hum", "60", {"unit_of_measurement": "%"})
    entry = make_entry(hass, **{CONF_HUMIDITY_ENTITY: "sensor.hum"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    saves = []
    monkeypatch.setattr(c.store, "schedule_save", lambda *a, **k: saves.append(1))
    for v in range(50, 60):
        hass.states.async_set("sensor.hum", str(v), {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert saves == []


@pytest.mark.asyncio
async def test_a_day_with_hours_of_temperature_missing_gives_no_et0(hass):
    from .test_et0_days import _day, full_temperature

    c = await _zone(hass)
    s = c.store.state
    day = dt_util.now().date() - timedelta(days=1)
    start = dt_util.start_of_local_day(day).timestamp()
    s.today_min_temp_c, s.today_peak_temp_c = 14.0, 27.0
    s.day_aggregates["temperature"] = _day(start, [(10 * 3600.0, 20.0)], 0)  # only the last 14 h
    c._close_et0_day(day, start + 86400)
    assert s.et0_day_history[0]["et0"] is None
    full_temperature(s, day)
    c._close_et0_day(day, start + 86400)
    assert s.et0_day_history[0]["et0"] > 0


@pytest.mark.asyncio
async def test_a_solar_sensor_that_is_offline_at_night_is_used_and_a_midday_gap_is_not(hass):
    from custom_components.zoneflow.const import CONF_SOLAR_ENTITY

    from .test_et0_days import _day, full_temperature

    await _seed_source_entities(hass)
    hass.states.async_set("sensor.sun", "300", {"unit_of_measurement": "W/m²"})
    entry = make_entry(hass, **{CONF_SOLAR_ENTITY: "sensor.sun"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    s = c.store.state
    day = dt_util.now().date() - timedelta(days=1)
    start = dt_util.start_of_local_day(day).timestamp()
    H = 3600.0
    s.today_min_temp_c, s.today_peak_temp_c = 14.0, 27.0
    full_temperature(s, day)
    # reports 06:00-18:00 only, offline (None) before and after
    s.day_aggregates["solar"] = _day(start, [(0, None), (6 * H, 400.0), (18 * H, None)], 0)
    c._close_et0_day(day, start + 86400)
    assert s.et0_day_history[0]["sources"]["solar"] == "measured"
    assert s.et0_day_history[0]["rs"] == pytest.approx(400 * 12 * H / 1e6, abs=0.05)
    # a 6 h gap in the middle of the day: not measured
    s.day_aggregates["solar"] = _day(start, [(6 * H, 400.0), (9 * H, None), (15 * H, 400.0), (18 * H, None)], 0)
    c._close_et0_day(day, start + 86400)
    assert s.et0_day_history[0]["sources"]["solar"] == "estimated"


@pytest.mark.asyncio
async def test_a_zone_that_is_watering_is_not_reloaded_by_the_other_writes(hass, fake_valve_services):
    from homeassistant.exceptions import ServiceValidationError

    c = await _zone(hass)
    c.store.state.lock_on = True  # a run is on
    assert c.run_in_progress
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "create_area", {"name": "Busy beds", "entity_id": "select.test_zone_water_demand_model"}, blocking=True
        )
    assert err.value.translation_key == "zone_busy"


@pytest.mark.asyncio
async def test_the_settings_forms_refuse_while_the_zone_is_watering(hass, fake_valve_services):
    c = await _zone(hass)
    c.store.state.lock_on = True
    result = await hass.config_entries.options.async_init(c.entry.entry_id)
    assert result["type"] == "abort" and result["reason"] == "zone_busy"
    c.store.state.lock_on = False
    result = await hass.config_entries.options.async_init(c.entry.entry_id)
    assert result["type"] != "abort"


@pytest.mark.asyncio
async def test_the_demand_model_select_follows_a_change_made_elsewhere(hass):
    from custom_components.zoneflow.const import DEMAND_MODEL_FAO56

    c = await _zone(hass)
    entity_id = "select.test_zone_water_demand_model"
    c.store.state.demand_model = "temperature_tiers"
    c._notify_status()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "temperature_tiers"
    c.store.state.demand_model = DEMAND_MODEL_FAO56
    c._notify_status()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == DEMAND_MODEL_FAO56


@pytest.mark.asyncio
async def test_a_daytime_solar_outage_cannot_hide_behind_the_night_zeros(hass):
    from custom_components.zoneflow.const import CONF_SOLAR_ENTITY

    from .test_et0_days import _day, full_temperature

    await _seed_source_entities(hass)
    hass.states.async_set("sensor.sun", "300", {"unit_of_measurement": "W/m²"})
    entry = make_entry(hass, **{CONF_SOLAR_ENTITY: "sensor.sun"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    s = c.store.state
    day = dt_util.now().date() - timedelta(days=1)
    start = dt_util.start_of_local_day(day).timestamp()
    H = 3600.0
    s.today_min_temp_c, s.today_peak_temp_c = 14.0, 27.0
    full_temperature(s, day)
    # zeros all night, then offline from 10:00 to 17:00: the night alone is 12 h of "coverage"
    s.day_aggregates["solar"] = _day(start, [(0, 0.0), (6 * H, 400.0), (10 * H, None), (17 * H, 300.0), (18 * H, 0.0)], 0)
    c._close_et0_day(day, start + 86400)
    assert s.et0_day_history[0]["sources"]["solar"] == "estimated"
