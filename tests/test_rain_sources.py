"""Rain gauge sensor types (1.6.5): besides a tip counter, a running total in
mm (lifetime, daily or weekly -- Ecowitt, Ambient Weather, Tempest ...), also
in inches, and a rain rate in mm/h that is added up over time."""
from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow.const import (
    CONF_RAIN_SOURCE,
    DOMAIN,
    RAIN_SOURCE_RATE,
    RAIN_SOURCE_TOTAL,
)

from .test_manual_rain import _setup
from .test_smoke_setup import RAIN_COUNTER


async def _set(hass, value, unit="mm"):
    hass.states.async_set(RAIN_COUNTER, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def _zone(hass, tmp_path, source, first, unit="mm"):
    entry, controller = await _setup(hass, csv_path=str(tmp_path / "f.csv"), **{CONF_RAIN_SOURCE: source})
    # A sensor that already has a value when ZoneFlow starts (the helper sets
    # the entity to 0 first): the history starts from that value.
    state = controller.store.state
    state.rain_samples = []
    state.rain_counter_drop_from = state.rain_counter_drop_ts = None
    state.rain_rate_last_mm_h = state.rain_rate_last_ts = None
    if source == RAIN_SOURCE_RATE:
        state.rain_counter_total_tips = 0.0
        state.rain_counter_last_tips = 0.0
    else:
        factor = 25.4 if unit == "in" else 1.0
        state.rain_counter_total_tips = state.rain_counter_last_tips = first * factor
    await _set(hass, first, unit)
    return entry, controller


@pytest.mark.asyncio
async def test_a_lifetime_total_in_mm_adds_only_the_increase(hass, tmp_path):
    _entry, controller = await _zone(hass, tmp_path, RAIN_SOURCE_TOTAL, 1234.5)
    assert controller.rain_windows()["24h"] == 0.0  # a high total is no rain by itself
    await _set(hass, 1235.0)
    await _set(hass, 1236.7)
    assert controller.rain_windows()["24h"] == pytest.approx(2.2)


@pytest.mark.asyncio
async def test_a_daily_total_that_resets_at_midnight(hass, tmp_path):
    _entry, controller = await _zone(hass, tmp_path, RAIN_SOURCE_TOTAL, 5.0)
    await _set(hass, 12.0)  # +7 mm
    await _set(hass, 0.0)  # midnight: back to zero, no rain
    await _set(hass, 0.4)
    assert controller.rain_windows()["24h"] == pytest.approx(7.4)


@pytest.mark.asyncio
async def test_a_total_in_inches_is_read_as_mm(hass, tmp_path):
    _entry, controller = await _zone(hass, tmp_path, RAIN_SOURCE_TOTAL, 10.0, "in")
    await _set(hass, 10.2, "in")
    assert controller.rain_windows()["24h"] == pytest.approx(0.2 * 25.4)


@pytest.mark.asyncio
async def test_the_tip_size_does_not_matter_for_a_total(hass, tmp_path):
    _entry, controller = await _zone(hass, tmp_path, RAIN_SOURCE_TOTAL, 100.0)
    await controller.numbers["rain_mm_per_tip"].async_set_metric_value(0.5)
    await _set(hass, 101.0)
    assert controller.rain_windows()["24h"] == pytest.approx(1.0)


class _Clock:
    """The controller's own clock, moved by hand (the rest of Home Assistant
    keeps real time)."""

    def __init__(self):
        self.t = dt_util.utcnow()

    def __getattr__(self, name):
        return getattr(dt_util, name)

    def utcnow(self):
        return self.t


@pytest.mark.asyncio
async def test_a_rain_rate_is_added_up_over_time(hass, tmp_path, monkeypatch):
    from custom_components.zoneflow import controller as controller_module

    clock = _Clock()
    monkeypatch.setattr(controller_module, "dt_util", clock)
    _entry, controller = await _zone(hass, tmp_path, RAIN_SOURCE_RATE, 6.0)
    clock.t += timedelta(minutes=10)
    await _set(hass, 0.0)  # 6 mm/h for 10 minutes = 1 mm
    assert controller.rain_windows()["24h"] == pytest.approx(1.0, abs=0.01)
    clock.t += timedelta(hours=3)
    await _set(hass, 12.0)  # the rate was 0 meanwhile: nothing added
    clock.t += timedelta(hours=3)
    await _set(hass, 0.0)  # a rate that went quiet counts 15 minutes at most: 3 mm
    assert controller.rain_windows()["24h"] == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
async def test_changing_the_source_starts_the_rain_history_again(hass, tmp_path):
    _entry, controller = await _zone(hass, tmp_path, RAIN_SOURCE_TOTAL, 100.0)
    await _set(hass, 105.0)
    assert controller.rain_windows()["24h"] == pytest.approx(5.0)
    controller.entry.data = {**controller.entry.data, CONF_RAIN_SOURCE: "tips"}
    controller._reset_rain_if_source_changed()
    assert controller.store.state.rain_samples == []
    assert controller.store.state.rain_counter_total_tips is None


@pytest.mark.asyncio
async def test_the_tip_size_setting_is_hidden_for_a_total(hass, tmp_path):
    from custom_components.zoneflow import visibility

    _entry, controller = await _zone(hass, tmp_path, RAIN_SOURCE_TOTAL, 1.0)
    assert ("number", "rain_mm_per_tip") in visibility.hidden_for(controller)


@pytest.mark.asyncio
async def test_rain_per_reading_is_added_up_including_repeated_readings(hass, tmp_path):
    from homeassistant.core import State

    _entry, controller = await _zone(hass, tmp_path, "amount_mm", 0.0)
    await _set(hass, 0.2)  # a change
    # The same 0.2 again is a reading too (a state report, not a change).
    controller._sync_rain_from_counter_state(State(RAIN_COUNTER, "0.2", {"unit_of_measurement": "mm"}))
    controller._sync_rain_from_counter_state(State(RAIN_COUNTER, "0.0", {"unit_of_measurement": "mm"}))
    await _set(hass, 0.1)
    assert controller.rain_windows()["24h"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_rain_per_reading_in_inches(hass, tmp_path):
    _entry, controller = await _zone(hass, tmp_path, "amount_mm", 0.0, "in")
    await _set(hass, 0.01, "in")
    assert controller.rain_windows()["24h"] == pytest.approx(0.254)


def test_two_heavy_days_in_a_row_on_a_daily_total_are_not_read_as_a_glitch():
    """25 mm, back to 0 at midnight, then the next day's total rises 24 -> 27
    in one reading: that is rain, not a glitch ending (the count would have
    to jump back to near yesterday's level from near zero)."""
    from custom_components.zoneflow import calculations as calc

    total, last, drop_from, drop_ts, since = 25.0, 25.0, None, None, 0.0
    now = 1_000_000.0
    total, last, drop_from, drop_ts, since = calc.track_tip_total(total, last, drop_from, drop_ts, since, 0.0, now, 0.5)
    for value in (6.0, 18.0, 24.0, 27.0):
        now += 600
        total, last, drop_from, drop_ts, since = calc.track_tip_total(
            total, last, drop_from, drop_ts, since, value, now, 0.5
        )
    assert total == pytest.approx(25.0 + 27.0)  # yesterday's 25 and today's 27


def test_a_real_glitch_on_a_total_is_still_recognised():
    from custom_components.zoneflow import calculations as calc

    total, last, drop_from, drop_ts, since = 1000.0, 1000.0, None, None, 0.0
    now = 1_000_000.0
    total, last, drop_from, drop_ts, since = calc.track_tip_total(total, last, drop_from, drop_ts, since, 0.0, now, 0.5)
    total, last, drop_from, drop_ts, since = calc.track_tip_total(total, last, drop_from, drop_ts, since, 1002.0, now + 3600, 0.5)
    assert total == pytest.approx(1002.0)


@pytest.mark.asyncio
async def test_rain_today_starts_at_zero_when_the_first_reading_arrives_after_startup(hass, tmp_path):
    entry, controller = await _setup(hass, csv_path=str(tmp_path / "f.csv"))
    state = controller.store.state
    state.rain_samples = []
    state.rain_counter_total_tips = state.rain_counter_last_tips = None
    state.rain_midnight_baseline_mm = 0.0
    hass.states.async_set(RAIN_COUNTER, "436")  # the sensor was unavailable at startup, now reports
    await hass.async_block_till_done()
    assert controller.today_rain_mm() == pytest.approx(0.0, abs=0.01)
    hass.states.async_set(RAIN_COUNTER, "437")
    await hass.async_block_till_done()
    assert controller.today_rain_mm() == pytest.approx(0.2997, abs=0.01)


@pytest.mark.asyncio
async def test_an_attribute_only_change_is_not_a_new_rain_reading(hass, tmp_path):
    _entry, controller = await _zone(hass, tmp_path, "amount_mm", 0.0)
    hass.states.async_set(RAIN_COUNTER, "0.2", {"unit_of_measurement": "mm", "note": "a"})
    await hass.async_block_till_done()
    hass.states.async_set(RAIN_COUNTER, "0.2", {"unit_of_measurement": "mm", "note": "b"})  # attribute only
    await hass.async_block_till_done()
    assert controller.rain_windows()["24h"] == pytest.approx(0.2)
