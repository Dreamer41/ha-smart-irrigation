"""Values that were fixed leftovers of the first YAML and are now settings (1.7.4):
the deficit mode range, the minimum pulse lengths, self-tuning (on/off, presses,
step), the weekly summary and fertilizing reminder times (asked at setup), and a
due buffer that follows how long the last watering took."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow import config_flow, summary, visibility
from custom_components.zoneflow.const import (
    CONF_FERTILIZE_TIME,
    CONF_SUMMARY_TIME,
    DOMAIN,
    NUMBER_DEFAULTS,
    NUMBER_DEFS,
)

from .test_scenarios_cycles import _history, _set, _zone
from .test_smoke_setup import VALVE, _seed_source_entities, make_entry
from .test_summary_repairs_pause_until import _seed as _seed_summary
from .test_summary_repairs_pause_until import _zone as _summary_zone
from .test_summary_repairs_pause_until import sent  # noqa: F401 - the notify fixture


def _switch(hass, entity_id):
    """The switch entity itself (the suite's fake valve services own switch.turn_on/off)."""
    from homeassistant.helpers.entity_component import DATA_INSTANCES

    return hass.data[DATA_INSTANCES]["switch"].get_entity(entity_id)


# --- deficit mode: 30 to 100 -----------------------------------------------
def test_deficit_mode_can_go_down_to_30_percent():
    assert NUMBER_DEFS["deficit_water_pct"][1:3] == (30.0, 100.0)
    kw = dict(enabled=True, until_ts=None, now_ts=1000.0, avg_peak_temp=25.0, hot_threshold=31.5,
              moisture_pct=None, dry_pct=20.0)
    assert calc.deficit_factor(water_pct=30, **kw) == (0.3, "active")
    assert calc.deficit_factor(water_pct=10, **kw) == (0.3, "active")  # never below 30 %
    assert calc.deficit_factor(water_pct=130, **kw) == (1.0, "active")


# --- the due buffer ----------------------------------------------------------
def test_the_buffer_is_six_hours_or_the_length_of_the_last_run_plus_an_hour():
    six = 6 * 3600
    assert calc.due_buffer_seconds(six, 0.0) == six
    assert calc.due_buffer_seconds(six, 3600.0) == six  # a short run: the base buffer
    assert calc.due_buffer_seconds(six, 9 * 3600) == 10 * 3600  # a long soak: the run plus an hour
    assert calc.due_buffer_seconds(six, 30 * 3600) == 20 * 3600  # never near a day


@pytest.mark.parametrize("gap", range(1, 11))
@pytest.mark.parametrize("run_hours", [0.5, 2.0, 5.5, 8.0, 12.0])
def test_a_watering_fires_on_its_day_however_long_the_last_one_took(gap, run_hours):
    """Watering at the same time every day, stamped when it finishes: the next one
    is due on day `gap` at that time, not a day later, and not the day before."""
    run = run_hours * 3600
    buffer = calc.due_buffer_seconds(6 * 3600, run)
    on_day = gap * 86400 - run  # the same clock time `gap` days later, measured from the finish
    day_before = (gap - 1) * 86400 - run
    assert calc.routine_due(on_day, gap, buffer)
    assert not calc.routine_due(day_before, gap, buffer)


@pytest.mark.asyncio
async def test_the_zone_remembers_how_long_the_last_watering_took(hass, fake_valve_services, monkeypatch, tmp_path):
    import homeassistant.util.dt as dt_util

    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    state = controller.store.state
    now = dt_util.utcnow().timestamp()
    state.last_routine_ts = now
    assert controller._routine_buffer() == 6 * 3600
    controller._remember_run_length(now - 9 * 3600, deep=False)  # it took nine hours
    assert controller._routine_buffer() == 10 * 3600
    state.last_routine_ts = now + 5  # stamped by something else (rain, mark watered): the length is stale
    assert controller._routine_buffer() == 6 * 3600
    state.last_deep_soak_ts = now
    controller._remember_run_length(now - 7 * 3600, deep=True)
    assert controller._deep_buffer() == 8 * 3600 and controller._routine_buffer() == 8 * 3600


@pytest.mark.asyncio
async def test_a_routine_watering_stamps_its_own_length(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    state = controller.store.state
    assert state.last_routine_run_for_ts == state.last_routine_ts
    assert state.last_routine_run_seconds >= 0.0


# --- minimum pulse length ----------------------------------------------------
def test_minimum_pulse_defaults_are_the_old_fixed_values():
    assert (NUMBER_DEFAULTS["routine_min_pulse_minutes"], NUMBER_DEFAULTS["deep_soak_min_pulse_minutes"]) == (1.0, 5.0)


@pytest.mark.asyncio
async def test_the_minimum_pulse_decides_how_many_pulses_a_small_dose_gets(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    controller.store.state.soil_type_override = "sandy"
    await _set(controller, routine_pulse_count=3.0, flow_rate_mm_per_min=0.1)
    assert controller._manual_pulses(6)[:2] == (3, 2.0)  # 1-minute floor: three pulses of two
    await _set(controller, routine_min_pulse_minutes=4.0)
    assert controller._manual_pulses(6)[:2] == (1, 6.0)  # four-minute floor: one pulse
    assert ("number", "routine_min_pulse_minutes") not in visibility.hidden_for(controller)
    # and the backup timer follows it: fewer, longer pulses
    await _set(controller, routine_min_pulse_minutes=1.0)
    short = controller.valve_open_times()["routine_minutes"]
    await _set(controller, routine_min_pulse_minutes=10.0)
    assert controller.valve_open_times()["routine_minutes"] >= short


@pytest.mark.asyncio
async def test_the_deep_soak_minimum_pulse_is_a_setting_hidden_without_deep_soak(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    assert ("number", "deep_soak_min_pulse_minutes") not in visibility.hidden_for(controller)
    controller.entry.options = {**controller.entry.options, "deep_soak_enabled": False}
    assert ("number", "deep_soak_min_pulse_minutes") in visibility.hidden_for(controller)


# --- self-tuning -------------------------------------------------------------
@pytest.mark.asyncio
async def test_self_tuning_can_be_switched_off(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    entity = next(s.entity_id for s in hass.states.async_all("switch") if s.entity_id.endswith("_self_tuning"))
    assert hass.states.get(entity).state == "on"  # on to start with, as it always was
    start = controller.number("routine_drydown_days")
    switch = _switch(hass, entity)
    await switch.async_turn_off()
    assert controller.store.state.self_tune_enabled is False
    for _ in range(6):
        await controller._register_self_tune_signal("early")
    assert controller.number("routine_drydown_days") == start and controller.store.state.self_tune_early_streak == 0
    await switch.async_turn_on()
    for _ in range(3):
        await controller._register_self_tune_signal("early")
    assert controller.number("routine_drydown_days") == start - 0.5


@pytest.mark.asyncio
async def test_self_tuning_presses_and_step_are_settings(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    await _set(controller, routine_drydown_days=5.0, self_tune_streak=2.0, self_tune_step_days=1.0)
    await controller._register_self_tune_signal("skip")
    assert controller.number("routine_drydown_days") == 5.0  # one press of two
    await controller._register_self_tune_signal("skip")
    assert controller.number("routine_drydown_days") == 6.0  # two presses: a one-day step longer


# --- summary and reminder times, asked at setup -------------------------------
def test_the_setup_forms_ask_for_both_times():
    schema = config_flow._schema({})
    keys = {str(k.schema) for k in schema.schema}
    assert {CONF_SUMMARY_TIME, CONF_FERTILIZE_TIME} <= keys
    filled = schema({k: v for k, v in {"valve_entity": "switch.v"}.items()})
    assert filled[CONF_SUMMARY_TIME] == "18:00:00" and filled[CONF_FERTILIZE_TIME] == "09:00:00"


@pytest.mark.asyncio
async def test_the_weekly_summary_goes_out_at_the_zones_own_time(hass, fake_valve_services, tmp_path, sent):  # noqa: F811
    await _seed_summary(hass)
    zone = await _summary_zone(hass, tmp_path, "Chilis", notify_entity="notify.phone", summary_time="07:30:00")
    zone.store.state.summary_day = "wed"
    assert (zone.summary_time.hour, zone.summary_time.minute) == (7, 30)
    assert await summary.async_send(hass, day="wed", at=(18, 0)) == 0  # the old fixed hour: not for this zone
    assert await summary.async_send(hass, day="wed", at=(7, 30)) == 1
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_the_fertilizing_reminder_follows_its_setup_time(hass, fake_valve_services, tmp_path):
    hass.states.async_set(VALVE, "off")
    entry = make_entry(hass, csv_path=str(tmp_path / "f.csv"), fertilize_reminder_time="06:45:00")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    assert (zone.fertilize_time.hour, zone.fertilize_time.minute) == (6, 45)


@pytest.mark.asyncio
async def test_a_zone_set_up_before_has_the_old_times(hass, fake_valve_services):
    await _seed_source_entities(hass)
    entry = make_entry(hass)  # no times in its data: a zone from 1.7.3
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    assert (zone.summary_time.hour, zone.fertilize_time.hour) == (18, 9)


# --- the card shows every new setting ------------------------------------------
def test_the_card_places_the_new_settings():
    card = (Path(__file__).parent.parent / "custom_components" / "zoneflow" / "frontend" / "zoneflow-card.js").read_text(
        encoding="utf-8"
    )
    groups = card[card.index("const SETTINGS_GROUPS"):card.index("const HANDLED")]
    for key in (
        "number.routine_min_pulse_minutes", "number.deep_soak_min_pulse_minutes", "switch.self_tuning",
        "number.self_tune_streak", "number.self_tune_step_days",
    ):
        assert re.search(rf'"{re.escape(key)}"', groups), key
