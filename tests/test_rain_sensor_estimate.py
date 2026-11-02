"""1.8: rain estimated from a binary rain sensor. A zone with no rain gauge and no Weather Underground
counts Rain Sensor Rain Rate for every hour the sensor reads wet, as it goes; at most 30 mm a day; a gauge
measures instead; a wet spell over a restart counts up to the last heartbeat; 0 is off."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import setup_check, visibility, why
from custom_components.zoneflow.const import CONF_RAIN_COUNTER_ENTITY, CONF_RAIN_SENSOR_ENTITY

from .test_pause_and_frost import _zone

SENSOR = "binary_sensor.garden_rain"


class Clock:
    def __init__(self, monkeypatch):
        self.now = dt_util.utcnow()
        monkeypatch.setattr(dt_util, "utcnow", lambda: self.now)

    def ahead(self, **kw):
        self.now += timedelta(**kw)
        return self.now.timestamp()


async def _estimating(hass, monkeypatch, tmp_path, rate=2.0, **overrides):
    hass.states.async_set(SENSOR, "off")
    c = await _zone(hass, monkeypatch, tmp_path, **{CONF_RAIN_SENSOR_ENTITY: SENSOR, CONF_RAIN_COUNTER_ENTITY: None, **overrides})
    await c.numbers["rain_sensor_mm_per_hour"].async_set_metric_value(rate)
    return c


@pytest.mark.asyncio
async def test_wet_time_counts_as_rain(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _estimating(hass, monkeypatch, tmp_path)
    clock = Clock(monkeypatch)
    start = clock.now.timestamp()
    assert c.rain_estimate_active and c._rain_between_mm(start - 60, start + 1) == 0.0
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    c._on_heartbeat(None)  # rain counted as it falls, at each heartbeat
    t = clock.ahead(minutes=30)
    c._on_heartbeat(None)
    assert c._rain_between_mm(start - 60, t + 1) == pytest.approx(1.0)
    assert c.rain_windows()["30min"] == pytest.approx(1.0)  # "raining now" counts it too
    t = clock.ahead(minutes=60)
    hass.states.async_set(SENSOR, "off")
    await hass.async_block_till_done()
    assert c._rain_between_mm(start - 60, t + 1) == pytest.approx(3.0)
    t = clock.ahead(hours=2)  # dry: nothing more
    c._on_heartbeat(None)
    assert c._rain_between_mm(start - 60, t + 1) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_no_day_gets_more_than_30_mm(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _estimating(hass, monkeypatch, tmp_path, rate=10.0)
    clock = Clock(monkeypatch)
    start = clock.now.timestamp()
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    for _ in range(30):  # five hours in ten-minute steps: 50 mm at the rate
        clock.ahead(minutes=10)
        c._on_heartbeat(None)
    end = clock.now.timestamp()
    day_start = dt_util.start_of_local_day(dt_util.as_local(clock.now)).timestamp()
    assert c._rain_between_mm(day_start, end + 1) <= 30.0 + 1e-6
    if start >= day_start:  # the five hours did not cross midnight
        assert c._rain_between_mm(start - 60, end + 1) == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_off_at_zero_and_a_gauge_measures_instead(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _estimating(hass, monkeypatch, tmp_path, rate=0.0)
    assert not c.rain_estimate_active
    assert ("number", "rain_sensor_mm_per_hour") not in visibility.hidden_for(c)
    levels = {item["id"]: item for item in setup_check.run_checks(c)}
    assert levels["rain"]["level"] == "info" and "Rain Sensor Rain Rate" in levels["rain"]["text"]


@pytest.mark.asyncio
async def test_a_zone_with_a_rain_gauge_does_not_estimate(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(SENSOR, "on")
    c = await _zone(hass, monkeypatch, tmp_path, **{CONF_RAIN_SENSOR_ENTITY: SENSOR})
    await c.numbers["rain_sensor_mm_per_hour"].async_set_metric_value(2.0)
    assert c.rain_counter_entity and not c.rain_estimate_active
    assert ("number", "rain_sensor_mm_per_hour") in visibility.hidden_for(c)


@pytest.mark.asyncio
async def test_a_wet_spell_over_a_restart_counts_up_to_the_last_heartbeat(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _estimating(hass, monkeypatch, tmp_path)
    clock = Clock(monkeypatch)
    start = clock.now.timestamp()
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    state = c.store.state
    state.last_alive_ts = clock.ahead(minutes=30)  # the last heartbeat before Home Assistant stopped
    now = clock.ahead(hours=3)  # down for hours: unknown, not counted
    c._count_sensor_rain(now, until_ts=state.last_alive_ts)
    assert c._rain_between_mm(start - 60, now + 1) == pytest.approx(1.0)
    assert state.rain_sensor_wet_since == pytest.approx(now)  # still wet: counted again from now


@pytest.mark.asyncio
async def test_why_says_the_rain_is_estimated(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _estimating(hass, monkeypatch, tmp_path)
    texts = " ".join(item["text"] for item in why.explain(c))
    assert "estimated from the rain sensor" in texts
    levels = {item["id"]: item for item in setup_check.run_checks(c)}
    assert levels["rain"]["level"] == "ok" and "2.0 mm/h" in levels["rain"]["text"]
