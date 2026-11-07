"""1.8: watering by the flow meter (Watering Stops On = Flow meter). Each pulse ends when its share of the
litres has gone through; the planned time plus the allowance is the limit. A meter that stops counting
falls back to time, far too much water closes the valve, and a run that can't give its litres in time
warns of low flow. Time mode waters as before, with correct litres for rate meters."""
from __future__ import annotations

import asyncio

import pytest
from homeassistant.core import callback

from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow import visibility
from custom_components.zoneflow.const import (
    CONF_FLOW_METER_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    DELIVERY_FLOW,
    DELIVERY_TIME,
)

from .test_scenarios_cycles import _history, _zone
from .test_smoke_setup import VALVE

METER = "sensor.zone_meter"


class FakeMeter:
    """Counts while the zone valve is open: `per_tick` litres (or reports `rate` L/min) every tick."""

    def __init__(self, hass, unit="L", per_tick=1.0, rate=None, counting=True):
        self.hass, self.unit, self.per_tick, self.rate, self.counting = hass, unit, per_tick, rate, counting
        self.total = 100.0
        self._task = None
        hass.states.async_set(METER, str(rate if rate is not None else self.total), {"unit_of_measurement": unit})

        @callback
        def on_valve(event):
            new = event.data.get("new_state")
            if event.data["entity_id"] == VALVE and new is not None and new.state == "on" and self._task is None:
                self._task = hass.async_create_task(self._run())

        hass.bus.async_listen("state_changed", on_valve)

    async def _run(self):
        try:
            while (s := self.hass.states.get(VALVE)) is not None and s.state == "on":
                await asyncio.sleep(0.02)
                if not self.counting:
                    continue
                if self.rate is not None:
                    self.hass.states.async_set(METER, str(self.rate), {"unit_of_measurement": self.unit}, force_update=True)
                else:
                    self.total += self.per_tick
                    self.hass.states.async_set(METER, str(self.total), {"unit_of_measurement": self.unit})
        finally:
            self._task = None


async def _flow_zone(hass, monkeypatch, tmp_path, *, area=2.0, mode=DELIVERY_FLOW, **meter):
    hass.states.async_set(METER, "100", {"unit_of_measurement": meter.get("unit", "L")})
    c, clock, events = await _zone(hass, monkeypatch, tmp_path, **{CONF_FLOW_METER_ENTITY: METER, CONF_PUMP_POWER_ENTITY: None})
    _history(c, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await c.numbers["zone_area_m2"].async_set_metric_value(area)
    c.store.state.delivery_mode = mode
    fake = FakeMeter(hass, **meter)
    return c, clock, events, fake


@pytest.mark.asyncio
async def test_each_pulse_stops_at_its_share_of_the_litres(hass, fake_valve_services, monkeypatch, tmp_path):
    c, clock, events, fake = await _flow_zone(hass, monkeypatch, tmp_path)
    assert c.flow_delivery_problem() is None
    plan = c._routine_plan()
    target = plan.needed_mm * 2.0
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Routine Irrigation Completed" in events
    given = fake.total - 100.0
    assert target <= given <= target + plan.pulse_count  # each pulse stops within one tick past its share
    assert c.store.state.last_cycle_liters == pytest.approx(given, abs=1.0)
    assert hass.states.get(VALVE).state == "off" and not c.store.state.lock_on
    done = c.store.state.decisions["routine"]
    assert done["code"] == "done" and done["params"]["amount_mm"] == pytest.approx(c.store.state.last_cycle_liters / 2.0, abs=0.1)  # what the meter counted


@pytest.mark.asyncio
async def test_a_meter_that_never_counts_falls_back_to_time(hass, fake_valve_services, monkeypatch, tmp_path):
    monkeypatch.setattr(controller_module, "FLOW_START_GRACE_SECONDS", 0.2)
    c, clock, events, fake = await _flow_zone(hass, monkeypatch, tmp_path, counting=False)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Flow Meter Not Counting" in events and "Routine Irrigation Completed" in events
    assert events.count("Flow Meter Not Counting") == 1
    assert "No Flow Detected" not in events  # said once already
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_far_too_much_water_closes_the_valve(hass, fake_valve_services, monkeypatch, tmp_path):
    monkeypatch.setattr(controller_module, "FLOW_HIGH_SECONDS", 0.05)
    c, clock, events, fake = await _flow_zone(hass, monkeypatch, tmp_path, unit="L/min", rate=100.0)
    await c.numbers["zone_flow_l_min"].async_set_metric_value(5.0)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Flow Too High" in events and "Routine Irrigation Completed" not in events
    assert hass.states.get(VALVE).state == "off" and not c.store.state.lock_on


@pytest.mark.asyncio
async def test_a_run_short_of_its_litres_at_the_time_limit_warns_of_low_flow(hass, fake_valve_services, monkeypatch, tmp_path):
    c, clock, events, fake = await _flow_zone(hass, monkeypatch, tmp_path, unit="L/min", rate=0.5)
    monkeypatch.setattr(c, "_flow_pulse_limit_minutes", lambda kind, pulse, count: 0.01)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Low Flow" in events and "Routine Irrigation Completed" in events
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_time_mode_is_unchanged_and_a_rate_meter_is_not_read_as_litres(hass, fake_valve_services, monkeypatch, tmp_path):
    c, clock, events, fake = await _flow_zone(hass, monkeypatch, tmp_path, mode=DELIVERY_TIME, unit="L/min", rate=6.0)
    assert c.flow_delivery_problem() == "off"
    assert await c._flow_meter_reading() is None  # 6 L/min is not a total of 6 litres
    plan = c._routine_plan()
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Routine Irrigation Completed" in events
    assert clock.valve_minutes(VALVE) == pytest.approx(plan.pulse_count * plan.pulse_runtime_minutes)


@pytest.mark.asyncio
async def test_why_a_zone_cannot_water_by_its_meter(hass, fake_valve_services, monkeypatch, tmp_path):
    c, clock, events, fake = await _flow_zone(hass, monkeypatch, tmp_path, area=0.0)
    await c.numbers["zone_flow_l_min"].async_set_metric_value(0.0)
    assert c.flow_delivery_problem() == "no_area"
    await c.numbers["zone_flow_l_min"].async_set_metric_value(6.0)
    assert c.zone_area_m2() == pytest.approx(6.0 / c.number("flow_rate_mm_per_min"))  # worked out from Zone Flow
    assert c.flow_delivery_problem() is None
    hass.states.async_set(METER, "12", {"unit_of_measurement": "pulses"})
    assert c.flow_delivery_problem() == "unknown_unit"
    hass.states.async_set(METER, "unavailable")
    assert c.flow_delivery_problem() == "meter_offline"


@pytest.mark.asyncio
async def test_flow_mode_lets_a_pulse_run_to_its_limit_for_the_valve_timer(hass, fake_valve_services, monkeypatch, tmp_path):
    c, clock, events, fake = await _flow_zone(hass, monkeypatch, tmp_path, mode=DELIVERY_TIME)
    timed = c.valve_open_times()["longest_minutes"]
    assert ("number", "flow_time_allowance_pct") in visibility.hidden_for(c)
    c.store.state.delivery_mode = DELIVERY_FLOW
    assert c.valve_open_times()["longest_minutes"] >= timed
    assert ("number", "flow_time_allowance_pct") not in visibility.hidden_for(c)


def test_the_pulse_limit():
    class Fake:
        def number(self, key):
            return {"flow_time_allowance_pct": 50.0, "max_runtime_minutes": 30.0, "deep_soak_max_runtime_minutes": 120.0}[key]

    limit = controller_module.ZoneFlowController._flow_pulse_limit_minutes
    assert limit(Fake(), "Routine Irrigation", 4.0, 3) == pytest.approx(6.0)
    assert limit(Fake(), "Routine Irrigation", 9.0, 3) == pytest.approx(10.0)  # 30 min cap over 3 pulses
    assert limit(Fake(), "Routine Irrigation", 12.0, 3) == pytest.approx(12.0)  # never shorter than planned
