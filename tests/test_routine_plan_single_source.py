"""The routine watering, the hourly "watered by the rain" check and the
Status estimate work the dose out in one place (_routine_plan), so they can
never disagree about how much a routine watering gives."""
from __future__ import annotations

from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

DAY = 86400.0


async def _zone(hass):
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "0"), (OUTDOOR_TEMP, "29.0")):
        hass.states.async_set(entity, value)
    await hass.async_block_till_done()
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    c._run_pulses = AsyncMock(return_value=True)
    return c


def _record(monkeypatch):
    seen = []
    real = calc.plan_routine_irrigation

    def spy(**kwargs):
        seen.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(calc, "plan_routine_irrigation", spy)
    return seen


@pytest.mark.asyncio
async def test_the_routine_and_the_estimate_use_the_same_dose(hass, fake_valve_services, monkeypatch):
    c = await _zone(hass)
    # A due zone with some rain, deficit mode and a growth ramp on: every input that shapes the dose.
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 5 * DAY
    c.store.state.last_significant_rain_ts = 0.0
    c.store.state.rain_day_history_mm = [3.0, 1.0] + [0.0] * 8
    c.store.state.deficit_enabled = True
    await c.numbers["target_weekly_mm"].async_set_metric_value(31.0)
    seen = _record(monkeypatch)

    estimate = c._routine_plan()
    await c.run_routine_irrigation()

    assert len(seen) == 2, "the routine must work its dose out through _routine_plan"
    routine_args, estimate_args = seen[1], seen[0]
    routine_args.pop("days_elapsed"), estimate_args.pop("days_elapsed")  # a moment apart: the same whole day
    assert routine_args == estimate_args
    c._run_pulses.assert_called_once()
    assert c._run_pulses.call_args.kwargs["runtime_for_log"] == estimate.calc_runtime_minutes


@pytest.mark.asyncio
async def test_a_run_brought_forward_by_a_dry_probe_gets_its_share(hass, fake_valve_services):
    c = await _zone(hass)
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 1 * DAY
    full = c._routine_plan()
    share = c._routine_plan(interval_fraction=0.25)
    assert share.interval_target_mm == pytest.approx(full.interval_target_mm * 0.25)
