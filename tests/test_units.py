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


# --- step 2: sensors, flow meter, messages ----------------------------------

def _sensor_entity(hass, fragment):
    st = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith(fragment))
    return next(e for e in hass.data["sensor"].entities if e.entity_id == st.entity_id)


@pytest.mark.asyncio
async def test_imperial_zone_sensors_show_inches_fahrenheit_and_in_per_day(hass, fake_valve_services, tmp_path):
    _, c = await _zone(hass, tmp_path, ha_units=US_CUSTOMARY_SYSTEM)
    await hass.config.async_update(latitude=9.5)
    s = c.store.state
    s.peak_temp_day_history_c = [31.0, 31.0, 31.0]
    s.min_temp_day_history_c = [24.0, 24.0, 24.0]
    hass.states.async_set(RAIN_COUNTER, "10")  # 3 mm
    await hass.async_block_till_done()

    rain = _sensor_entity(hass, "rain_past_24h")
    target = _sensor_entity(hass, "routine_weekly_target")
    temp = _sensor_entity(hass, "3_day_average_peak_temperature")
    et0 = _sensor_entity(hass, "reference_et0_3_day_avg")
    assert (rain.native_unit_of_measurement, rain.native_value) == ("in", pytest.approx(3.0 / 25.4))
    assert (target.native_unit_of_measurement, target.native_value) == ("in", pytest.approx(35.0 / 25.4))
    assert (temp.native_unit_of_measurement, temp.native_value) == ("°F", pytest.approx(87.8))
    assert et0.native_unit_of_measurement == "in/d"
    assert et0.native_value == pytest.approx(c.avg_et0() / 25.4)
    assert target.device_class == "precipitation" and et0.device_class == "precipitation_intensity"


@pytest.mark.asyncio
async def test_metric_zone_sensors_are_unchanged(hass, fake_valve_services, tmp_path):
    await _zone(hass, tmp_path)
    target = _sensor_entity(hass, "routine_weekly_target")
    assert (target.native_unit_of_measurement, target.native_value) == ("mm", 35.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("ha_units,shown,unit", [(METRIC_SYSTEM, 37.9, "L"), (US_CUSTOMARY_SYSTEM, 10.0, "gal")])
async def test_a_flow_meter_in_gallons_is_read_in_its_own_unit(hass, fake_valve_services, monkeypatch, tmp_path, ha_units, shown, unit):
    """The flow meter's reading used to be taken as litres whatever its
    unit; a gallon meter was under-read 3.8x."""
    meter = "sensor.flow_meter_gallons"
    hass.states.async_set(meter, "100", {"unit_of_measurement": "gal"})
    hass.config.units = ha_units
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"), flow_meter_entity=meter)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    clock = CompressedTime(hass, [VALVE]).install(monkeypatch)

    async def ten_gallons(index):
        if index == 2:
            hass.states.async_set(meter, "110", {"unit_of_measurement": "gal"})

    clock.on_pulse = ten_gallons
    _history(c, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await c.run_routine_irrigation()
    await hass.async_block_till_done()

    assert c.store.state.last_cycle_water_liters == pytest.approx(37.854, abs=0.01)
    water = _sensor_entity(hass, "last_cycle_water_delivered_measured")
    assert water.native_unit_of_measurement == unit
    assert water.native_value == pytest.approx(shown, abs=0.05)


@pytest.mark.asyncio
@pytest.mark.parametrize("ha_units,expected", [(METRIC_SYSTEM, "20.0 mm"), (US_CUSTOMARY_SYSTEM, "0.79 in")])
async def test_phone_messages_use_the_zones_units(hass, fake_valve_services, monkeypatch, tmp_path, ha_units, expected):
    sent = []

    async def _notify(call):
        sent.append(call.data["message"])

    hass.services.async_register("notify", "send_message", _notify)
    hass.config.units = ha_units
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"), notify_entity="notify.phone")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    CompressedTime(hass, [VALVE]).install(monkeypatch)
    _history(c, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await c.run_routine_irrigation()
    await hass.async_block_till_done()

    assert any(f"Target: {expected}" in m for m in sent), sent
    # The CSV log stays metric either way, so its history never mixes units.
    assert ",20.0," in (tmp_path / "u.csv").read_text()
