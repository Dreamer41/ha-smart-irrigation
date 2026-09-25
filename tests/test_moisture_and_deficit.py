"""Soil moisture made visible (status, estimates, log) and deficit mode
(regulated deficit irrigation) with its guardrails.

Normal tier with a 4-day gap delivers 35 mm x 4 / 7 = 20 mm, so deficit
mode at 50% should deliver 10 mm, and every guardrail should bring it back
to the full 20 mm.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
import homeassistant.util.dt as dt_util

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import DEMAND_MODEL_ET, DOMAIN

from .test_scenarios_cycles import _delivered_mm, _history, _set, _tolerance_mm, _zone
from .test_smoke_setup import VALVE

SOIL = "sensor.soil_probe"
DAY = 86400.0


async def _moist_zone(hass, monkeypatch, tmp_path, moisture="40"):
    hass.states.async_set(SOIL, moisture)
    return await _zone(hass, monkeypatch, tmp_path, soil_moisture_entity=SOIL)


def _sensor(hass, fragment):
    return next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith(fragment))


async def _refresh(hass):
    from homeassistant.setup import async_setup_component

    await async_setup_component(hass, "homeassistant", {})
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {"entity_id": [s.entity_id for s in hass.states.async_all("sensor") if "test_zone" in s.entity_id]},
        blocking=True,
    )


# ---------------------------------------------------------------------------
# Soil moisture: visible
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_moisture_sensors_exist_only_for_a_zone_with_a_probe(hass, fake_valve_services, monkeypatch, tmp_path):
    await _zone(hass, monkeypatch, tmp_path)
    ids = [s.entity_id for s in hass.states.async_all("sensor")]
    assert not any("soil_moisture" in i for i in ids)


@pytest.mark.asyncio
@pytest.mark.parametrize("reading,status", [("15", "dry"), ("40", "in_range"), ("75", "wet"), ("unavailable", "offline")])
async def test_moisture_status_says_what_the_next_run_will_do(
    hass, fake_valve_services, monkeypatch, tmp_path, reading, status
):
    await _moist_zone(hass, monkeypatch, tmp_path, moisture=reading)
    await _refresh(hass)
    st = _sensor(hass, "soil_moisture_status")
    assert st.state == status
    assert st.attributes["dry_threshold_pct"] == 20.0 and st.attributes["wet_threshold_pct"] == 60.0
    level = _sensor(hass, "_soil_moisture")
    if reading == "unavailable":
        assert level.state == "unknown"
    else:
        assert float(level.state) == float(reading)


@pytest.mark.asyncio
async def test_wet_soil_skipping_a_due_run_is_logged_not_silent(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _moist_zone(hass, monkeypatch, tmp_path, moisture="75")
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == []
    assert events == ["Routine Skipped (Soil Wet)"]


@pytest.mark.asyncio
async def test_wet_soil_on_a_day_that_was_not_due_anyway_logs_nothing(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _moist_zone(hass, monkeypatch, tmp_path, moisture="75")
    _history(controller, last_routine_days_ago=1, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reading,decided_by,days", [("75", "soil_wet", None), ("15", "soil_dry", 0.0), ("40", "schedule", 3.0)])
async def test_the_next_run_estimate_follows_the_soil(
    hass, fake_valve_services, monkeypatch, tmp_path, reading, decided_by, days
):
    controller, _, _ = await _moist_zone(hass, monkeypatch, tmp_path, moisture=reading)
    _history(controller, last_routine_days_ago=1, peaks=(30.5, 30.5, 30.5))
    await _refresh(hass)
    nxt = _sensor(hass, "next_irrigation_estimate")
    assert nxt.attributes["decided_by"] == decided_by
    assert (nxt.state == "unknown") == (days is None)
    countdown = _sensor(hass, "days_until_next_run")
    if days is None:
        assert countdown.attributes["routine_days"] is None
    else:
        assert countdown.attributes["routine_days"] == pytest.approx(days, abs=0.1)


@pytest.mark.asyncio
async def test_a_dry_forced_run_says_so_in_its_message(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _moist_zone(hass, monkeypatch, tmp_path, moisture="15")
    notes = controller._routine_notes(False, 15.0, 1.0, "off")
    assert "Soil moisture 15% (dry)" in notes
    assert controller._routine_notes(True, 15.0, 1.0, "off") == ""


# ---------------------------------------------------------------------------
# Deficit mode
# ---------------------------------------------------------------------------

def test_deficit_factor_rules():
    kw = dict(enabled=True, water_pct=70, until_ts=None, now_ts=1000.0, avg_peak_temp=30.0,
              hot_threshold=31.5, moisture_pct=None, dry_pct=20.0)
    assert calc.deficit_factor(**kw) == (0.7, "active")
    assert calc.deficit_factor(**{**kw, "enabled": False}) == (1.0, "off")
    assert calc.deficit_factor(**{**kw, "until_ts": 999.0}) == (1.0, "ended")
    assert calc.deficit_factor(**{**kw, "avg_peak_temp": 32.0}) == (1.0, "full_dose_hot")
    assert calc.deficit_factor(**{**kw, "moisture_pct": 20.0}) == (1.0, "full_dose_soil_dry")
    assert calc.deficit_factor(**{**kw, "growth_ramp": 0.8}) == (1.0, "full_dose_young_plant")
    assert calc.deficit_factor(**{**kw, "water_pct": 20}) == (0.5, "active")  # never below 50%
    assert calc.deficit_factor(**{**kw, "avg_peak_temp": None}) == (0.7, "active")  # no temp sensor: no heat guard
    assert calc.deficit_factor(**{**kw, "avg_peak_temp": None, "temp_unavailable": True}) == (1.0, "full_dose_no_temp")


async def _deficit_zone(hass, monkeypatch, tmp_path, *, pct=50, peaks=(30.5, 30.5, 30.5), **zone_kw):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path, **zone_kw)
    _history(controller, last_routine_days_ago=4, peaks=peaks)
    await _set(controller, deficit_water_pct=pct)
    switch = next(s.entity_id for s in hass.states.async_all("switch") if s.entity_id.endswith("deficit_mode"))
    await _switch(hass, switch).async_turn_on()
    return controller, clock, events, switch


def _switch(hass, entity_id):
    """The switch entity itself -- the suite's fake valve services own
    switch.turn_on/turn_off, so the service can't reach it."""
    from homeassistant.helpers.entity_component import DATA_INSTANCES

    return hass.data[DATA_INSTANCES]["switch"].get_entity(entity_id)


@pytest.mark.asyncio
async def test_deficit_mode_trims_the_routine_dose(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events, _ = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(10.0, abs=_tolerance_mm(controller, 3))
    assert "Routine Irrigation Completed" in events
    await _refresh(hass)
    assert _sensor(hass, "deficit_mode_status").state == "active"
    assert _sensor(hass, "routine_weekly_target").attributes["deficit_pct"] == 50


@pytest.mark.asyncio
async def test_deficit_mode_gives_the_full_dose_on_a_hot_day(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _, _ = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50, peaks=(33.0, 34.0, 32.0))
    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 3 * DAY
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    hot_share = controller.number("target_weekly_hot_mm") * 3 / 7
    assert _delivered_mm(clock, controller) == pytest.approx(hot_share, abs=_tolerance_mm(controller, 3))
    assert controller.deficit()[1] == "full_dose_hot"


@pytest.mark.asyncio
async def test_deficit_mode_never_takes_the_soil_past_dry(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(SOIL, "18")
    controller, clock, _, _ = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50, soil_moisture_entity=SOIL)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_deficit_mode_leaves_a_young_plant_alone(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _, _ = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50)
    monkeypatch.setattr(controller, "growth_ramp_fraction", lambda: 0.8)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    # Only the growth ramp applies: 20 mm x 0.8.
    assert _delivered_mm(clock, controller) == pytest.approx(16.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_deficit_mode_also_trims_the_et_curve(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _, _ = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50, peaks=(31.0, 31.0, 31.0))
    await hass.config.async_update(latitude=9.5)
    controller.store.state.min_temp_day_history_c = [24.0, 24.0, 24.0]
    controller.store.state.demand_model = DEMAND_MODEL_ET
    await _set(controller, crop_coefficient=0.8)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    expected = controller.avg_et0() * 0.8 * 4 * 0.5
    assert _delivered_mm(clock, controller) == pytest.approx(expected, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_deficit_mode_never_touches_deep_soak(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _, _ = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=14)
    await _set(controller, deep_soak_max_runtime_minutes=150)
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(
        controller.number("deep_soak_target_mm"), abs=_tolerance_mm(controller, 3)
    )


@pytest.mark.asyncio
async def test_deficit_mode_switches_itself_off_after_its_end_date(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events, switch = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50)
    ends = next(s.entity_id for s in hass.states.async_all("datetime") if s.entity_id.endswith("deficit_mode_ends"))
    # A planned end date may be in the future.
    await hass.services.async_call(
        "datetime", "set_value", {"entity_id": ends, "datetime": dt_util.now() + timedelta(days=30)}, blocking=True
    )
    assert controller.store.state.deficit_until_ts is not None
    controller.store.state.deficit_until_ts = dt_util.utcnow().timestamp() - 60  # it has passed
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Deficit Mode Ended" in events
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))
    assert controller.store.state.deficit_enabled is False
    await _refresh(hass)
    await hass.services.async_call("homeassistant", "update_entity", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "off"


@pytest.mark.asyncio
async def test_turning_deficit_mode_on_again_clears_a_stale_end_date(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _, switch = await _deficit_zone(hass, monkeypatch, tmp_path)
    await _switch(hass, switch).async_turn_off()
    controller.store.state.deficit_until_ts = dt_util.utcnow().timestamp() - DAY
    await _switch(hass, switch).async_turn_on()
    assert controller.store.state.deficit_enabled is True
    assert controller.store.state.deficit_until_ts is None


@pytest.mark.asyncio
async def test_deficit_mode_survives_a_reload(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _, switch = await _deficit_zone(hass, monkeypatch, tmp_path, pct=60)
    entry = controller.entry
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    new = hass.data[DOMAIN][entry.entry_id]
    assert new.store.state.deficit_enabled is True
    assert new.number("deficit_water_pct") == 60
    assert hass.states.get(switch).state == "on"


@pytest.mark.asyncio
async def test_deficit_mode_does_not_cut_water_blind_when_the_temp_sensor_is_offline(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    from .test_smoke_setup import OUTDOOR_TEMP

    controller, clock, _, _ = await _deficit_zone(hass, monkeypatch, tmp_path, pct=50)
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    await hass.async_block_till_done()
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert controller.deficit()[1] == "full_dose_no_temp"
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))
