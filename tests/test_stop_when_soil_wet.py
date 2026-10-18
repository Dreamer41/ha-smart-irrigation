"""When Soil Gets Wet During Watering (1.7.4): with a soil probe, the person
chooses what a routine watering does when the probe reads the wet threshold or
more between pulses: "stop" there, or "finish" the planned pulses (the start,
as before)."""
from __future__ import annotations

import pytest

from custom_components.zoneflow import visibility
from custom_components.zoneflow.const import DOMAIN

from .test_scenarios_cycles import _history, _zone
from .test_smoke_setup import VALVE, _seed_source_entities, make_entry

SOIL = "sensor.soil_moisture_zone1"


async def _probe_zone(hass, monkeypatch, tmp_path, *, stop, start="40"):
    hass.states.async_set(SOIL, start)
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path, soil_moisture_entity=SOIL)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    controller.store.state.soil_wet_action = "stop" if stop else "finish"
    return controller, clock, events


def _wet_after_first_pulse(hass, clock, value="75"):
    async def hook(index):
        if index == 0:
            hass.states.async_set(SOIL, value)
            await hass.async_block_till_done()

    clock.on_pulse = hook


@pytest.mark.asyncio
async def test_a_wet_probe_stops_the_rest_and_the_watering_counts(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _probe_zone(hass, monkeypatch, tmp_path, stop=True)
    before = controller.store.state.last_routine_ts
    _wet_after_first_pulse(hass, clock)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    pulses = clock.pulses_for(VALVE)
    assert len(pulses) == 1
    state = controller.store.state
    assert hass.states.get(VALVE).state == "off" and state.lock_on is False
    assert state.last_routine_ts > before  # the soil got what it needed: this is the watering
    assert state.today_runtime_minutes == pytest.approx(pulses[0])  # and the cap counts the valve minutes
    assert state.last_cycle_runtime_min == pytest.approx(pulses[0])
    assert state.decisions["routine"]["code"] == "done"
    assert "Routine Irrigation Stopped (Soil Wet)" in events
    assert "Routine Irrigation Completed" not in events


@pytest.mark.asyncio
async def test_set_to_finish_it_gives_every_pulse_as_before(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _probe_zone(hass, monkeypatch, tmp_path, stop=False)
    _wet_after_first_pulse(hass, clock)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3
    assert "Routine Irrigation Completed" in events


@pytest.mark.asyncio
async def test_soil_that_stays_under_the_wet_level_does_not_stop_it(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _probe_zone(hass, monkeypatch, tmp_path, stop=True)
    _wet_after_first_pulse(hass, clock, value="55")  # under the 60 % wet threshold
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3
    assert "Routine Irrigation Completed" in events


@pytest.mark.asyncio
async def test_a_probe_that_drops_out_mid_run_does_not_stop_it(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _probe_zone(hass, monkeypatch, tmp_path, stop=True)
    _wet_after_first_pulse(hass, clock, value="unavailable")
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3
    assert "Routine Irrigation Completed" in events


@pytest.mark.asyncio
async def test_a_manual_press_is_the_persons_decision_and_is_not_cut_short(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _probe_zone(hass, monkeypatch, tmp_path, stop=True)
    _wet_after_first_pulse(hass, clock)
    await controller.run_routine_now()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3
    assert "Routine Irrigation Completed" in events


@pytest.mark.asyncio
async def test_the_choice_is_remembered_and_only_shown_with_a_probe(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _probe_zone(hass, monkeypatch, tmp_path, stop=False)
    entity = next(s.entity_id for s in hass.states.async_all("select") if s.entity_id.endswith("soil_gets_wet_during_watering"))
    assert hass.states.get(entity).state == "finish"
    await hass.services.async_call("select", "select_option", {"entity_id": entity, "option": "stop"}, blocking=True)
    assert controller.store.state.soil_wet_action == "stop" and hass.states.get(entity).state == "stop"
    assert ("select", "soil_wet_action") not in visibility.hidden_for(controller)


@pytest.mark.asyncio
async def test_without_a_probe_the_choice_is_hidden(hass, fake_valve_services):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert ("select", "soil_wet_action") in visibility.hidden_for(controller)


@pytest.mark.asyncio
async def test_yesterdays_soil_stop_is_not_taken_for_a_run_that_never_started(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """A routine run that never gets to open the valve (here the zone is stopping) must not
    be recorded as done because the run before it was stopped by wet soil."""
    controller, clock, events = await _probe_zone(hass, monkeypatch, tmp_path, stop=True)
    _wet_after_first_pulse(hass, clock)
    await controller.run_routine_irrigation()  # day 1: stopped by the wet soil
    await hass.async_block_till_done()
    assert controller._last_outcome == "soil" and controller._delivered_minutes > 0

    state = controller.store.state
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    stamp = state.last_routine_ts
    clock.on_pulse = None
    hass.states.async_set(SOIL, "40")  # the soil has dried: a watering is due again
    await hass.async_block_till_done()
    async def never_started(**kwargs):  # day 2: due, but it queues for a shared pump and is paused before it opens
        return False

    controller._run_pulses = never_started
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert state.last_routine_ts == stamp  # nothing was watered, so nothing is marked done
