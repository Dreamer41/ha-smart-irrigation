"""Temperature tiers outside the tropics, the Fallback / Manual Temperature
slider, and the hot/cool threshold sliders.

ZoneFlow started as a Koh Samui avocado automation, where any afternoon
below 15C meant a broken sensor. In most of the world that is ordinary
spring weather, and must count as a real (cool) day.
"""
import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.zoneflow.const import CONF_INITIAL_NUMBERS, DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

TEMPERATE = {"hot_temp_threshold": 28.0, "cool_temp_threshold": 20.0, "fallback_temp": 24.0}


async def _zone(hass, **entry_kw):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, 999)
    hass.states.async_set(RAIN_COUNTER, 0)
    hass.states.async_set(OUTDOOR_TEMP, 12.0)
    await hass.async_block_till_done()
    entry = make_entry(hass, **entry_kw)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _entity_id(hass, domain, suffix):
    return next(s.entity_id for s in hass.states.async_all(domain) if s.entity_id.endswith(suffix))


def _live_day(controller, peak, low=None):
    """A day with real readings, recorded by the 23:59:50 shift."""
    controller.store.state.today_peak_temp_c = peak
    controller.store.state.today_min_temp_c = low if low is not None else peak - 8
    controller._on_daily_shift(None)


@pytest.mark.asyncio
async def test_a_cold_spring_week_is_the_cool_tier_not_a_made_up_30(hass, fake_valve_services):
    """Regression: 12C afternoons were dropped as "corrupt", the average fell
    back to 30C, and a temperate zone got the normal (or with tropical
    thresholds, near-hot) dose in cold weather."""
    controller = await _zone(hass, **{CONF_INITIAL_NUMBERS: TEMPERATE})
    for peak in (11.0, 13.0, 12.0):
        _live_day(controller, peak)
    assert controller.avg_peak_temp() == pytest.approx(12.0)
    assert controller.watering_temp() == (pytest.approx(12.0), "sensor")
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_cool_mm")

    # A warm spell: normal, then hot.
    for peak in (24.0, 25.0, 23.0):
        _live_day(controller, peak)
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_mm")
    for peak in (30.0, 31.0, 29.0):
        _live_day(controller, peak)
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_hot_mm")


@pytest.mark.asyncio
async def test_frost_and_below_zero_days_count(hass, fake_valve_services):
    controller = await _zone(hass, **{CONF_INITIAL_NUMBERS: TEMPERATE})
    for peak in (-3.0, 0.0, 2.0):
        _live_day(controller, peak, low=peak - 6)
    assert controller.watering_temp() == (pytest.approx(-1 / 3, abs=0.01), "sensor")


@pytest.mark.asyncio
async def test_avg_peak_sensor_is_unknown_without_real_days_and_shows_what_is_used(hass, fake_valve_services):
    controller = await _zone(hass, **{CONF_INITIAL_NUMBERS: TEMPERATE})
    entity_id = _entity_id(hass, "sensor", "3_day_average_peak_temperature")
    ent = next(e for e in hass.data["sensor"].entities if e.entity_id == entity_id)

    controller.store.state.peak_temp_day_history_c = [None, None, None]
    ent.async_write_ha_state()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "unknown"  # not 30C dressed up as a reading
    assert state.attributes["watering_temperature"] == 24.0
    assert state.attributes["temperature_source"] == "fallback"
    assert state.attributes["temperature_tier"] == "normal"

    _live_day(controller, 14.0)
    ent.async_write_ha_state()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(14.0)
    assert state.attributes["temperature_source"] == "sensor"
    assert state.attributes["temperature_tier"] == "cool"


@pytest.mark.asyncio
async def test_older_zone_gets_its_fallback_seeded_once_and_it_stays(hass, fake_valve_services):
    """A zone from before the slider existed keeps the normal tier it always
    fell back to: its fallback is set once to the middle of its own band,
    then behaves like any slider -- the same value after a reload, and not
    dragged along when the thresholds move later."""
    controller = await _zone(hass)
    assert controller.fallback_temp() == pytest.approx(30.75)  # between cool 30 and hot 31.5
    entity_id = _entity_id(hass, "number", "fallback_manual_temperature")
    assert float(hass.states.get(entity_id).state) == pytest.approx(30.75)

    entry = controller.entry
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.fallback_temp() == pytest.approx(30.75, abs=0.05)
    controller.store.state.peak_temp_day_history_c = [None, None, None]
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_mm")


@pytest.mark.asyncio
async def test_older_zone_with_cool_not_below_hot_stays_on_the_normal_tier(hass, fake_valve_services, hass_storage):
    """The old slider ranges allowed cool == hot. Such a zone has no normal
    band to seed a fallback in: it stays unset, which means the normal tier
    it always fell back to -- not a midpoint that lands in the hot tier."""
    from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data
    from homeassistant.core import State

    entry = make_entry(hass)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("number.test_zone_hot_weather_temp_threshold", "30.0"),
                {"native_value": 30.0, "native_min_value": 15.0, "native_max_value": 45.0,
                 "native_step": 0.5, "native_unit_of_measurement": "°C"},
            ),
            (
                State("number.test_zone_cool_weather_temp_threshold", "30.0"),
                {"native_value": 30.0, "native_min_value": 5.0, "native_max_value": 40.0,
                 "native_step": 0.5, "native_unit_of_measurement": "°C"},
            ),
        ],
    )
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, 999)
    hass.states.async_set(RAIN_COUNTER, 0)
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.number("hot_temp_threshold") == controller.number("cool_temp_threshold") == 30.0

    assert controller.fallback_temp() is None
    assert controller.watering_temp() == (None, "fallback")
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_mm")
    entity_id = _entity_id(hass, "number", "fallback_manual_temperature")
    assert hass.states.get(entity_id).state == "unknown"


@pytest.mark.asyncio
async def test_new_zone_first_day_uses_the_fallback_and_says_why(hass, fake_valve_services):
    """Before the first 23:59:50 shift a brand-new zone has no full day on
    record even with a working sensor: the setup fallback decides, and
    nothing calls the sensor offline."""
    controller = await _zone(hass, **{CONF_INITIAL_NUMBERS: TEMPERATE})
    assert controller.watering_temp() == (24.0, "fallback")
    controller.store.state.deficit_enabled = True
    assert controller.deficit()[1] == "full_dose_no_temp"
    notes = controller._routine_notes(True, None, 1.0, "full_dose_no_temp")
    assert "no temperature reading on record" in notes and "offline" not in notes


@pytest.mark.asyncio
async def test_zone_without_sensor_drops_made_up_history(hass, fake_valve_services):
    """Before 1.4.2 a zone without a sensor filled its peak history with a
    made-up 30C. That isn't real data: it is cleared, so a sensor added
    later starts from real readings only."""
    controller = await _zone(hass, outdoor_temp_entity=None)
    controller.store.state.peak_temp_day_history_c = [30.0, 30.0, 30.0]
    await controller.store.async_save()
    entry = controller.entry
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.store.state.peak_temp_day_history_c == [None, None, None]
    assert controller.avg_peak_temp() is None


def test_season_simulator_script_runs():
    """The README's season simulator must survive days with no temperature
    history (the average is None now, not 30)."""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "simulate_season.py"
    result = subprocess.run([sys.executable, str(script), "--days", "8"], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_cool_threshold_must_stay_below_hot(hass, fake_valve_services):
    controller = await _zone(hass, **{CONF_INITIAL_NUMBERS: TEMPERATE})
    with pytest.raises(ServiceValidationError):
        await controller.numbers["cool_temp_threshold"].async_set_native_value(28.0)
    with pytest.raises(ServiceValidationError):
        await controller.numbers["hot_temp_threshold"].async_set_native_value(19.5)
    assert controller.number("cool_temp_threshold") == 20.0
    assert controller.number("hot_temp_threshold") == 28.0
    # Moving both down works in the right order.
    await controller.numbers["cool_temp_threshold"].async_set_native_value(15.0)
    await controller.numbers["hot_temp_threshold"].async_set_native_value(22.0)
    assert (controller.number("cool_temp_threshold"), controller.number("hot_temp_threshold")) == (15.0, 22.0)


@pytest.mark.asyncio
async def test_thresholds_reach_nordic_and_desert_values(hass, fake_valve_services):
    controller = await _zone(hass)
    num_hot = controller.numbers["hot_temp_threshold"]
    num_cool = controller.numbers["cool_temp_threshold"]
    assert num_cool.native_min_value <= 10.0 and num_hot.native_min_value <= 20.0
    assert num_hot.native_max_value >= 42.0


@pytest.mark.asyncio
async def test_setup_values_survive_a_restart_as_the_sliders_own(hass, fake_valve_services):
    """The setup values only seed the sliders: after the person moves a
    slider, a reload keeps the slider's value, not the setup one."""
    controller = await _zone(hass, **{CONF_INITIAL_NUMBERS: TEMPERATE})
    await controller.numbers["fallback_temp"].async_set_native_value(31.0)
    entry = controller.entry
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].number("fallback_temp") == 31.0


@pytest.mark.asyncio
async def test_a_working_sensor_that_never_changes_still_records_its_day(hass, fake_valve_services):
    """Some sensors only report on change. A day with no change is still a
    real reading -- recorded as the day's peak (not as "no reading"), with
    no minimum, so ET0 doesn't invent a zero temperature range."""
    controller = await _zone(hass, **{CONF_INITIAL_NUMBERS: TEMPERATE})
    for _ in range(3):
        controller.store.state.today_peak_temp_c = None
        controller.store.state.today_min_temp_c = None
        controller._on_daily_shift(None)  # sensor sat at 12.0 all day
    assert controller.store.state.peak_temp_day_history_c == [12.0, 12.0, 12.0]
    assert controller.store.state.min_temp_day_history_c == [None, None, None]
    assert controller.watering_temp() == (12.0, "sensor")

    # An offline sensor, on the other hand, records nothing.
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    await hass.async_block_till_done()
    controller.store.state.today_peak_temp_c = None
    controller._on_daily_shift(None)
    assert controller.store.state.peak_temp_day_history_c[0] is None
