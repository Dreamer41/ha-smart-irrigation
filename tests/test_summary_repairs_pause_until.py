"""Weekly summary (summary.py), Repairs (issues.py), Paused Until, and the
frost guard reading the weather entity when there's no temperature sensor.
"""
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow import issues, summary, visibility
from custom_components.zoneflow.const import DOMAIN, SUMMARY_DAYS, SUMMARY_HOUR

from .scenario_harness import CompressedTime
from .test_scenarios_cycles import _history
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

VALVE_B = "switch.watering2"
WEATHER = "weather.home"
CATALOG = json.loads(
    (Path(__file__).parent.parent / "custom_components" / "zoneflow" / "messages" / "en.json").read_text(encoding="utf-8")
)
DAY = 86400


@pytest.fixture
def sent(hass):
    messages = []

    async def _notify(call):
        messages.append(dict(call.data))

    hass.services.async_register("notify", "send_message", _notify)
    return messages


async def _seed(hass):
    for entity, value in ((VALVE, "off"), (VALVE_B, "off"), (PUMP, "999"), (RAIN_COUNTER, "0"), (OUTDOOR_TEMP, "28.0")):
        hass.states.async_set(entity, value)
    hass.states.async_set("notify.phone", "unknown")
    hass.states.async_set("notify.tablet", "unknown")
    await hass.async_block_till_done()


async def _zone(hass, tmp_path, name, **overrides):
    entry = make_entry(hass, zone_name=name, csv_path=str(tmp_path / f"{name}.csv"), **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _issue(hass, controller, key):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{controller.entry.entry_id}_{key}")


# --- Weekly summary --------------------------------------------------------


@pytest.mark.asyncio
async def test_weekly_summary_one_message_per_phone(hass, fake_valve_services, monkeypatch, tmp_path, sent):
    await _seed(hass)
    a = await _zone(hass, tmp_path, "Chilis", notify_entity="notify.phone", pump_power_entity=None)
    b = await _zone(hass, tmp_path, "Avocado", valve_entity=VALVE_B, notify_entity="notify.phone", pump_power_entity=None)
    c = await _zone(hass, tmp_path, "Herbs", valve_entity="switch.w3", notify_entity="notify.tablet", pump_power_entity=None)
    hass.states.async_set("switch.w3", "off")
    CompressedTime(hass, [VALVE, VALVE_B]).install(monkeypatch)
    for zone in (a, b):
        zone.store.state.summary_day = "wed"
    c.store.state.summary_day = "thu"

    # A watering for Chilis, a refused one (daily cap) for Avocado.
    _history(a, last_routine_days_ago=4, last_deep_days_ago=1, peaks=(30.5, 30.5, 30.5))
    await a.run_routine_irrigation()
    _history(b, last_routine_days_ago=4, last_deep_days_ago=1)
    b.store.state.today_runtime_minutes = b.number("max_daily_runtime_minutes")
    await b.run_routine_irrigation()
    await hass.async_block_till_done()
    assert a.store.state.summary_runs == 1 and a.store.state.summary_mm > 0
    assert b.store.state.summary_skip_days == [dt_util.now().date().isoformat()]
    sent.clear()

    assert await summary.async_send(hass, day="wed") == 1
    assert len(sent) == 1 and sent[0]["entity_id"] == "notify.phone"
    assert sent[0]["title"] == CATALOG["summary"]["title"]
    lines = sent[0]["message"].split("\n")
    assert lines[0].startswith("Avocado: no watering") and "held back on 1 day(s)" in lines[0]
    assert lines[1].startswith("Chilis: watered 1×") and " · rain (7 days) 0.0 mm" in lines[1] and " · next " in lines[1]
    # Counters start over after a summary.
    assert a.store.state.summary_runs == 0 and b.store.state.summary_skip_days == []


@pytest.mark.asyncio
async def test_weekly_summary_goes_out_at_its_time(hass, fake_valve_services, tmp_path, sent):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis", notify_entity="notify.phone")
    now = dt_util.now()
    at = now.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=1)
    select_id = next(s.entity_id for s in hass.states.async_all("select") if s.entity_id.endswith("weekly_summary"))
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": SUMMARY_DAYS[at.weekday()]}, blocking=True
    )
    assert zone.store.state.summary_since_ts is not None
    async_fire_time_changed(hass, dt_util.as_utc(at) + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert len(sent) == 1 and sent[0]["message"].startswith("Chilis: no watering")


@pytest.mark.asyncio
async def test_preview_service_and_notification_level(hass, fake_valve_services, tmp_path, sent):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis", notify_entity="notify.phone")
    zone.store.state.summary_day = "mon"
    zone.store.state.summary_runs = 3
    await hass.services.async_call(DOMAIN, "send_weekly_summary", {}, blocking=True)
    assert len(sent) == 1 and "watered 3×" in sent[0]["message"]
    assert zone.store.state.summary_runs == 3  # a preview doesn't reset the week

    # Its own opt-in: sent even with the zone's other notifications off.
    zone.store.state.notify_level = "none"
    await hass.services.async_call(DOMAIN, "send_weekly_summary", {}, blocking=True)
    assert len(sent) == 2

    zone.store.state.summary_day = "off"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send_weekly_summary", {}, blocking=True)


@pytest.mark.asyncio
async def test_summary_settings_hidden_without_a_notify_target(hass, fake_valve_services, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    hidden = visibility.hidden_for(zone)
    assert ("select", "weekly_summary") in hidden and ("select", "notifications") in hidden


# --- Repairs ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_valve_and_sensor_issues_come_and_go(hass, fake_valve_services, monkeypatch, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    await zone.numbers["flow_rate_mm_per_min"].async_set_metric_value(0.3)
    hass.states.async_set(VALVE, "unavailable")
    hass.states.async_set(RAIN_COUNTER, "unavailable")
    hass.states.async_remove(OUTDOOR_TEMP)
    issues.async_check(zone)
    assert _issue(hass, zone, "valve_unavailable") is None  # not for an hour yet

    later = dt_util.utcnow() + timedelta(hours=2)
    monkeypatch.setattr(issues, "dt_util", SimpleNamespace(utcnow=lambda: later))
    issues.async_check(zone)
    issue = _issue(hass, zone, "valve_unavailable")
    assert issue is not None and issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_placeholders["entity"] == VALVE
    assert _issue(hass, zone, "sensor_offline_rain_gauge") is None  # sensors get 3 days

    much_later = dt_util.utcnow() + timedelta(days=4)
    monkeypatch.setattr(issues, "dt_util", SimpleNamespace(utcnow=lambda: much_later))
    issues.async_check(zone)
    assert _issue(hass, zone, "sensor_offline_rain_gauge") is not None
    assert _issue(hass, zone, "sensor_offline_temperature") is not None  # missing altogether
    assert _issue(hass, zone, "sensor_offline_pump_power") is None

    hass.states.async_set(VALVE, "off")
    hass.states.async_set(RAIN_COUNTER, "3")
    hass.states.async_set(OUTDOOR_TEMP, "20")
    issues.async_check(zone)
    for key in ("valve_unavailable", "sensor_offline_rain_gauge", "sensor_offline_temperature"):
        assert _issue(hass, zone, key) is None


@pytest.mark.asyncio
async def test_flow_rate_and_notify_issues(hass, fake_valve_services, monkeypatch, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis", notify_entity="notify.gone")
    issues.async_check(zone)
    assert _issue(hass, zone, "flow_rate_default") is not None
    number_id = next(s.entity_id for s in hass.states.async_all("number") if "flow_rate" in s.entity_id)
    await hass.services.async_call("number", "set_value", {"entity_id": number_id, "value": 0.3}, blocking=True)
    assert _issue(hass, zone, "flow_rate_default") is None  # cleared at once

    later = dt_util.utcnow() + timedelta(days=2)
    monkeypatch.setattr(issues, "dt_util", SimpleNamespace(utcnow=lambda: later))
    issues.async_check(zone)
    assert _issue(hass, zone, "notify_missing") is not None

    # Deleting the zone clears its issues.
    assert await hass.config_entries.async_remove(zone.entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, zone, "notify_missing") is None


@pytest.mark.asyncio
async def test_issues_are_checked_hourly(hass, fake_valve_services, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert _issue(hass, zone, "flow_rate_default") is not None


# --- Paused Until ----------------------------------------------------------


@pytest.mark.asyncio
async def test_paused_until_resumes_by_itself(hass, fake_valve_services, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    until_id = next(s.entity_id for s in hass.states.async_all("datetime") if s.entity_id.endswith("paused_until"))
    pause_id = next(s.entity_id for s in hass.states.async_all("switch") if s.entity_id.endswith("_pause"))
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "datetime", "set_value", {"entity_id": until_id, "datetime": dt_util.now() - timedelta(hours=1)}, blocking=True
        )
    until = (dt_util.now() + timedelta(days=3)).replace(microsecond=0)
    await hass.services.async_call("datetime", "set_value", {"entity_id": until_id, "datetime": until}, blocking=True)
    await hass.async_block_till_done()
    assert zone.paused and hass.states.get(pause_id).state == "on"
    assert dt_util.parse_datetime(hass.states.get(until_id).state) == dt_util.as_utc(until)
    assert zone.status()["text"].startswith("Paused until ")

    async_fire_time_changed(hass, dt_util.as_utc(until) + timedelta(seconds=2))
    await hass.async_block_till_done()
    assert not zone.paused
    assert hass.states.get(pause_id).state == "off"
    assert hass.states.get(until_id).state == "unknown"


@pytest.mark.asyncio
async def test_paused_until_survives_a_restart_and_ends_with_the_switch(hass, fake_valve_services, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    until_ts = dt_util.utcnow().timestamp() + 2 * DAY
    await zone.set_paused(True, until_ts=until_ts)
    assert await hass.config_entries.async_reload(zone.entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][zone.entry.entry_id]
    assert zone.paused and zone._resume_cancel is not None
    await zone.set_paused(False)
    assert zone.store.state.pause_until_ts is None and zone._resume_cancel is None


# --- Frost guard from the weather entity -----------------------------------


@pytest.mark.asyncio
async def test_frost_guard_uses_the_weather_entity_without_a_sensor(hass, fake_valve_services, tmp_path):
    await _seed(hass)
    hass.states.async_set(WEATHER, "cloudy", {"temperature": 0.5, "temperature_unit": "°C"})
    zone = await _zone(hass, tmp_path, "Chilis", outdoor_temp_entity=None, weather_entity=WEATHER)
    assert ("number", "frost_guard_temp") not in visibility.hidden_for(zone)
    assert zone._frost_temp_c() == 0.5
    hass.states.async_set(WEATHER, "cloudy", {"temperature": 30, "temperature_unit": "°F"})
    assert zone._frost_temp_c() == pytest.approx(-1.11, abs=0.01)
    hass.states.async_set(WEATHER, "unavailable", {})
    assert zone._frost_temp_c() is None


@pytest.mark.asyncio
async def test_held_back_counts_days_not_attempts(hass, fake_valve_services, monkeypatch, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis", notify_entity="notify.phone")
    CompressedTime(hass, [VALVE]).install(monkeypatch)
    _history(zone, last_routine_days_ago=5, last_deep_days_ago=20)
    zone.store.state.last_significant_rain_ts = dt_util.utcnow().timestamp() - 0.5 * DAY
    await zone.run_deep_soak()  # dry-down: held back
    await zone.run_routine_irrigation()  # dry-down: held back (same day)
    assert len(zone.store.state.summary_skip_days) == 1
    # "Run now" presses aren't counted at all.
    zone.store.state.summary_skip_days = []
    await zone.run_routine_now()
    assert zone.store.state.summary_skip_days == []
    # Held back, then watered the same day: not a held-back day.
    await zone.run_routine_irrigation()
    zone.store.state.last_significant_rain_ts = None
    _history(zone, last_routine_days_ago=5, last_deep_days_ago=1)
    await zone.run_routine_irrigation()
    await hass.async_block_till_done()
    assert zone.store.state.summary_runs == 1 and zone.store.state.summary_skip_days == []


@pytest.mark.asyncio
async def test_offline_time_survives_a_restart(hass, fake_valve_services, monkeypatch, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    hass.states.async_set(RAIN_COUNTER, "unavailable")
    issues.async_check(zone)
    first = zone.store.state.offline_since[RAIN_COUNTER]
    assert await hass.config_entries.async_reload(zone.entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][zone.entry.entry_id]
    hass.states.async_set(RAIN_COUNTER, "unavailable", force_update=True)
    later = dt_util.utcnow() + timedelta(days=4)
    monkeypatch.setattr(issues, "dt_util", SimpleNamespace(utcnow=lambda: later))
    issues.async_check(zone)
    assert zone.store.state.offline_since[RAIN_COUNTER] == first
    assert _issue(hass, zone, "sensor_offline_rain_gauge") is not None


@pytest.mark.asyncio
async def test_imperial_default_flow_rate_is_still_default(hass, fake_valve_services, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    await zone.numbers["flow_rate_mm_per_min"].async_set_metric_value(0.24002999)
    assert _issue(hass, zone, "flow_rate_default") is not None


@pytest.mark.asyncio
async def test_turning_pause_on_again_keeps_the_date(hass, fake_valve_services, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    until_ts = dt_util.utcnow().timestamp() + 2 * DAY
    await zone.set_paused(True, until_ts=until_ts)
    await zone.set_paused(True)
    assert zone.store.state.pause_until_ts == until_ts and zone._resume_cancel is not None


@pytest.mark.asyncio
async def test_a_paused_zone_raises_no_offline_repairs(hass, fake_valve_services, monkeypatch, tmp_path):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis")
    await zone.set_paused(True)
    hass.states.async_set(VALVE, "unavailable")
    later = dt_util.utcnow() + timedelta(days=4)
    monkeypatch.setattr(issues, "dt_util", SimpleNamespace(utcnow=lambda: later))
    issues.async_check(zone)
    assert _issue(hass, zone, "valve_unavailable") is None


@pytest.mark.asyncio
async def test_an_open_valve_alert_comes_through_with_notifications_off(hass, fake_valve_services, tmp_path, sent):
    await _seed(hass)
    zone = await _zone(hass, tmp_path, "Chilis", notify_entity="notify.phone")
    zone.store.state.notify_level = "none"
    await zone._log_event(
        event_type="Test", status="ERROR", target_mm=0.0, deducted_mm=0.0, runtime=0, notify_phone=True,
        message="cycle_error_open", params={"cycle": "x", "error": "y", "valve": VALVE}, level="warning",
        always_notify=True,
    )
    await zone._log_event(
        event_type="Test", status="Info", target_mm=0.0, deducted_mm=0.0, runtime=0, notify_phone=True,
        message="deficit_ended",
    )
    assert len(sent) == 1 and "OPEN" in sent[0]["message"]
