"""Metric / imperial display (units.py). ZoneFlow stores and calculates in
metric; only what the sliders show and accept changes. These tests check
the display, the round trip, the per-zone override, that switching units
never changes a setting, and that watering is identical either way.
"""
import pytest
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.zoneflow import units
from custom_components.zoneflow.const import CONF_UNIT_SYSTEM, DOMAIN, NUMBER_DEFS

from .scenario_harness import CompressedTime
from .test_scenarios_cycles import _history
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _zone(hass, tmp_path, *, ha_units=METRIC_SYSTEM, choice=None):
    hass.config.units = ha_units
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()
    extra = {CONF_UNIT_SYSTEM: choice} if choice else {}
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"), **extra)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]


def _state(hass, fragment):
    return next(s for s in hass.states.async_all("number") if s.entity_id.endswith(fragment))


async def _set(hass, fragment, value):
    await hass.services.async_call(
        "number", "set_value", {"entity_id": _state(hass, fragment).entity_id, "value": value}, blocking=True
    )


@pytest.mark.parametrize("key", sorted(units.DEPTH_KEYS | units.FLOW_KEYS | units.TEMP_KEYS))
def test_every_converted_slider_round_trips_and_keeps_its_range(key):
    _, lo, hi, step, _ = NUMBER_DEFS[key]
    for metric in (lo, (lo + hi) / 2, hi):
        assert units.to_metric(key, units.to_display(key, metric, True), True) == pytest.approx(metric)
    d_lo, d_hi = units.display_range(key, lo, hi, step, True)
    assert units.to_metric(key, d_lo, True) <= lo + 1e-9
    assert units.to_metric(key, d_hi, True) >= hi - 1e-9


@pytest.mark.asyncio
async def test_metric_home_assistant_shows_metric(hass, fake_valve_services, tmp_path):
    await _zone(hass, tmp_path)
    st = _state(hass, "routine_normal_weekly_target")
    assert st.attributes["unit_of_measurement"] == "mm" and float(st.state) == 35.0


@pytest.mark.asyncio
async def test_imperial_home_assistant_shows_inches_in_h_and_fahrenheit(hass, fake_valve_services, tmp_path):
    _, c = await _zone(hass, tmp_path, ha_units=US_CUSTOMARY_SYSTEM)
    target = _state(hass, "routine_normal_weekly_target")
    flow = _state(hass, "emitter_flow_rate_calibration")
    hot = _state(hass, "hot_weather_temp_threshold")
    assert (target.attributes["unit_of_measurement"], float(target.state)) == ("in", pytest.approx(1.378, abs=0.001))
    assert (flow.attributes["unit_of_measurement"], float(flow.state)) == ("in/h", pytest.approx(0.567, abs=0.001))
    assert (hot.attributes["unit_of_measurement"], float(hot.state)) == ("°F", pytest.approx(88.7, abs=0.05))
    # Untouched settings are still exactly the metric defaults internally.
    assert c.number("target_weekly_mm") == 35.0 and c.number("flow_rate_mm_per_min") == 0.24
    # Unconverted sliders stay as they are.
    assert _state(hass, "routine_dry_down_holdoff").attributes["unit_of_measurement"] == "d"


@pytest.mark.asyncio
async def test_values_typed_in_imperial_are_stored_as_exact_metric(hass, fake_valve_services, tmp_path):
    _, c = await _zone(hass, tmp_path, ha_units=US_CUSTOMARY_SYSTEM)
    await _set(hass, "routine_normal_weekly_target", 1.5)
    await _set(hass, "emitter_flow_rate_calibration", 0.6)
    await _set(hass, "hot_weather_temp_threshold", 90)
    assert c.number("target_weekly_mm") == pytest.approx(38.1)
    assert c.number("flow_rate_mm_per_min") == pytest.approx(0.6 * 25.4 / 60)
    assert c.number("hot_temp_threshold") == pytest.approx(32.222, abs=0.001)


@pytest.mark.asyncio
@pytest.mark.parametrize("ha_units,choice,unit", [
    (METRIC_SYSTEM, "imperial", "in"),
    (US_CUSTOMARY_SYSTEM, "metric", "mm"),
    (US_CUSTOMARY_SYSTEM, "auto", "in"),
])
async def test_the_zone_option_overrides_home_assistant(hass, fake_valve_services, tmp_path, ha_units, choice, unit):
    await _zone(hass, tmp_path, ha_units=ha_units, choice=choice)
    assert _state(hass, "routine_normal_weekly_target").attributes["unit_of_measurement"] == unit


@pytest.mark.asyncio
async def test_switching_units_never_changes_a_setting(hass, fake_valve_services, tmp_path):
    entry, c = await _zone(hass, tmp_path, ha_units=US_CUSTOMARY_SYSTEM)
    await _set(hass, "routine_normal_weekly_target", 1.5)       # 38.1 mm
    await _set(hass, "hot_weather_temp_threshold", 90)          # 32.2 °C
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_UNIT_SYSTEM: "metric"})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    c2 = hass.data[DOMAIN][entry.entry_id]
    assert c2.number("target_weekly_mm") == pytest.approx(38.1)
    assert c2.number("hot_temp_threshold") == pytest.approx(32.222, abs=0.001)
    st = _state(hass, "routine_normal_weekly_target")
    assert (st.attributes["unit_of_measurement"], float(st.state)) == ("mm", pytest.approx(38.1))


@pytest.mark.asyncio
@pytest.mark.parametrize("ha_units", [METRIC_SYSTEM, US_CUSTOMARY_SYSTEM])
async def test_watering_is_identical_in_metric_and_imperial(hass, fake_valve_services, monkeypatch, tmp_path, ha_units):
    _, c = await _zone(hass, tmp_path, ha_units=ha_units)
    clock = CompressedTime(hass, [VALVE]).install(monkeypatch)
    _history(c, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) == pytest.approx(83.0)  # 20 mm / 0.24 mm/min, same either way
