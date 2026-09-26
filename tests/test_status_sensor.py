"""The Status sensor ("why"): one plain-language sentence per zone, plus a
stable `code` attribute -- watering now, what a due cycle decided today
and why, a hold that's on right now, or when it waters next (at the
cycle's scheduled time, by the same due checks the cycles use).
"""
from datetime import timedelta

import pytest
from homeassistant.core import SupportsResponse
from homeassistant.helpers.sun import get_astral_event_next
import homeassistant.util.dt as dt_util
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.zoneflow import calculations as calc, messages
from custom_components.zoneflow.const import DOMAIN

from .scenario_harness import CompressedTime
from .test_scenarios_cycles import _history
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

SOIL = "sensor.soil_moisture_zone1"
WEATHER = "weather.home"
DAY = 86400


async def _zone(hass, monkeypatch, tmp_path, *, moisture=None, **overrides):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    if moisture is not None:
        hass.states.async_set(SOIL, moisture)
        overrides["soil_moisture_entity"] = SOIL
    await hass.async_block_till_done()
    entry = make_entry(hass, csv_path=str(tmp_path / "s.csv"), **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    controller.clock = CompressedTime(hass, [VALVE]).install(monkeypatch)
    return controller


def _sensor(hass):
    return next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("zone_status"))


async def _refresh(hass, controller):
    controller._notify_status()
    await hass.async_block_till_done()
    return _sensor(hass)


def _iso(ts):
    return dt_util.utc_from_timestamp(ts).isoformat()


@pytest.mark.asyncio
async def test_a_new_zone_says_when_it_first_waters(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "first_run"
    # Deep soak (05:00 in these tests) comes before the routine (05:30).
    assert state.state.startswith("First watering: deep soak ")
    assert state.state.endswith(" 05:00")
    assert state.attributes["friendly_name"].endswith("Status")

    # With deep soak off, the routine is first.
    monkeypatch.setattr(type(controller), "deep_soak_enabled", property(lambda self: False))
    state = await _refresh(hass, controller)
    assert state.state.startswith("First watering ") and state.state.endswith(" 05:30")


@pytest.mark.asyncio
async def test_completed_routine_shows_what_it_did_and_when_next(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    during = []

    async def on_pulse(index):
        during.append(controller.status()["code"])

    controller.clock.on_pulse = on_pulse
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=1, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    state = await _refresh(hass, controller)

    assert during and set(during) == {"watering"}  # while the valve ran
    assert state.attributes["code"] == "done"
    assert state.attributes["cycle"] == "routine"
    assert state.state.startswith("Routine watering done at ")
    assert " mm in " in state.state and " · next " in state.state
    assert state.attributes["next_cycle"] == "routine"
    assert state.attributes["decided_at"] is not None
    assert controller._cycle_kind == ""  # nothing running any more


@pytest.mark.asyncio
async def test_next_watering_is_the_scheduled_run_where_the_cycle_is_due(hass, fake_valve_services, monkeypatch, tmp_path):
    """A run finishes after its scheduled time; the next one is still due
    at the slot `interval` days later (the due check has a 6-hour buffer),
    not a day after that."""
    controller = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_deep_days_ago=1)
    now = dt_util.utcnow().timestamp()
    slot = controller.next_slot("routine", now + 2 * DAY)
    interval = calc.routine_interval_days(controller.effective_avg_peak_temp(), controller.number("hot_temp_threshold"))
    controller.store.state.last_routine_ts = slot - interval * DAY + 40 * 60  # finished 40 min after its slot
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "next"
    assert state.attributes["next_watering"] == _iso(slot)


@pytest.mark.asyncio
async def test_wet_soil_skip_says_why(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, moisture="80")
    _history(controller, last_routine_days_ago=5)
    await controller.run_routine_irrigation()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "skipped_soil_wet"
    assert state.attributes["cycle"] == "routine"
    assert state.state.startswith("Routine watering skipped at ")
    # Wet soil holds the routine back undated; the deep soak still has a date.
    assert ": the soil is wet (80%) · deep soak " in state.state
    assert state.state.endswith(" 05:00")


@pytest.mark.asyncio
async def test_wet_soil_without_a_decision_today_is_a_live_hold(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, moisture="80")
    _history(controller, last_routine_days_ago=1)
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "waiting_soil_wet"
    assert "80%" in state.state


@pytest.mark.asyncio
async def test_rain_drydown_skip_names_the_end(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    controller.store.state.last_significant_rain_ts = dt_util.utcnow().timestamp() - 0.5 * DAY
    await controller.run_routine_irrigation()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "skipped_drydown"
    assert ": drying out after rain until " in state.state
    # The next run is the first scheduled one after the dry-down.
    drydown_end = controller.store.state.last_significant_rain_ts + controller.number("routine_drydown_days") * DAY
    assert state.attributes["next_watering"] == _iso(controller.next_slot("routine", drydown_end))


@pytest.mark.asyncio
async def test_daily_cap_and_rain_credit_skips(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    controller.store.state.today_runtime_minutes = controller.number("max_daily_runtime_minutes")
    await controller.run_routine_irrigation()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "refused_daily_cap"
    assert "safety cap" in state.state

    # Plenty of rain over the interval: the rain credit covers the target.
    _history(controller, last_routine_days_ago=4)
    controller.store.state.rain_day_history_mm = [60.0] * len(controller.store.state.rain_day_history_mm)
    await controller.run_routine_irrigation()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "skipped_rain_credit"
    assert "covers the" in state.state


@pytest.mark.asyncio
async def test_forecast_skip(hass, fake_valve_services, monkeypatch, tmp_path):
    async def _get_forecasts(call):
        return {WEATHER: {"forecast": [{"precipitation": 12.0}]}}

    hass.services.async_register("weather", "get_forecasts", _get_forecasts, supports_response=SupportsResponse.ONLY)
    hass.states.async_set(WEATHER, "rainy")
    controller = await _zone(hass, monkeypatch, tmp_path, weather_entity=WEATHER)
    _history(controller, last_routine_days_ago=5)
    await controller.run_routine_irrigation()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "skipped_forecast"
    assert ": 12.0 mm of rain forecast" in state.state


@pytest.mark.asyncio
async def test_a_decision_from_yesterday_gives_way_to_the_next_run(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1)
    controller.store.state.decisions["routine"] = {
        "code": "skipped_soil_wet",
        "ts": (dt_util.now() - timedelta(days=1)).timestamp(),
        "params": {"pct": 75},
    }
    state = await _refresh(hass, controller)
    assert state.attributes["code"] in ("next", "next_deep_soak")
    assert state.attributes["next_watering"] is not None


@pytest.mark.asyncio
async def test_bad_stored_decisions_never_break_the_sensor(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=1)
    now = dt_util.utcnow().timestamp()
    for bad in (
        None,
        {"routine": "junk"},
        {"routine": {"code": "renamed_in_a_later_version", "ts": now}},
        {"routine": {"code": "skipped_soil_wet", "ts": "yesterday"}},
        {"routine": {"code": "skipped_soil_wet", "ts": now, "params": "junk"}},
    ):
        controller.store.state.decisions = bad
        status = controller.status()
        assert status["text"] and "status." not in status["text"], bad


@pytest.mark.asyncio
async def test_snooze_skips_todays_run_in_the_next_time(hass, fake_valve_services, monkeypatch, tmp_path):
    # The routine is due and its time is still ahead today (unless that's
    # already past midnight -- then it's tomorrow either way).
    later = dt_util.now() + timedelta(hours=2)
    controller = await _zone(hass, monkeypatch, tmp_path, routine_time=later.strftime("%H:%M:00"))
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    await controller.snooze_today()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "snoozed"
    assert state.state.startswith("Snoozed for today · next ")
    tomorrow = dt_util.as_utc(dt_util.start_of_local_day() + timedelta(days=1))
    assert dt_util.parse_datetime(state.attributes["next_watering"]) >= tomorrow

    controller._service_active = True
    assert controller.status()["code"] == "service_run"
    controller._service_active = False


@pytest.mark.asyncio
async def test_sun_relative_schedule(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, routine_sun_mode="after_sunrise", routine_sun_offset_minutes=30)
    now = dt_util.utcnow()
    expected = get_astral_event_next(hass, "sunrise", now - timedelta(minutes=30)) + timedelta(minutes=30)
    assert controller.next_slot("routine", now.timestamp()) == expected.timestamp()


@pytest.mark.asyncio
async def test_a_leftover_lock_is_explained(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    controller.store.state.lock_on = True
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "lock_held"
    controller.store.state.lock_on = False


@pytest.mark.asyncio
async def test_status_follows_units_and_language(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.config.units = US_CUSTOMARY_SYSTEM
    german = {
        "formats": {"weekday_time": "%a %H:%M", "days": "Mo,Di,Mi,Do,Fr,Sa,So"},
        "status": {"skipped_drydown": "{cycle} übersprungen um {time}: Abtrocknen nach Regen bis {until}"},
    }
    monkeypatch.setattr(messages, "_read", lambda language: german if language == "de" else None)
    hass.config.language = "de"
    controller = await _zone(hass, monkeypatch, tmp_path)
    rain_ts = dt_util.utcnow().timestamp() - 0.5 * DAY
    _history(controller, last_routine_days_ago=5)
    controller.store.state.last_significant_rain_ts = rain_ts
    await controller.run_routine_irrigation()
    state = await _refresh(hass, controller)

    until = dt_util.as_local(dt_util.utc_from_timestamp(rain_ts + controller.number("routine_drydown_days") * DAY))
    day = "Mo,Di,Mi,Do,Fr,Sa,So".split(",")[until.weekday()]
    assert f": Abtrocknen nach Regen bis {day} {until:%H:%M} · " in state.state

    # Units: a forecast skip reads in inches on an imperial zone.
    controller._record_decision("routine", "skipped_forecast", rain_mm=25.4)
    assert "1.00 in" in controller.status()["text"]


@pytest.mark.asyncio
async def test_decisions_survive_a_restart(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, moisture="80")
    _history(controller, last_routine_days_ago=5)
    await controller.run_routine_irrigation()
    entry = controller.entry
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _sensor(hass).attributes["code"] == "skipped_soil_wet"


@pytest.mark.asyncio
async def test_deep_soak_decisions(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=20)
    real_windows = controller.rain_windows
    # A wet fortnight holds a due deep soak back.
    controller.rain_windows = lambda: {**real_windows(), "14d": 200.0}
    await controller.run_deep_soak()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "skipped_wet_fortnight"
    assert state.attributes["cycle"] == "deep_soak"
    assert state.state.startswith("Deep soak held at ")
    assert ": 200.0 mm of rain in the last 14 days" in state.state

    controller.rain_windows = real_windows
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=20)
    await controller.run_deep_soak()
    state = await _refresh(hass, controller)
    assert state.attributes["code"] == "done"
    assert state.state.startswith("Deep soak done at ")
