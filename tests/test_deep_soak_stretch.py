"""A due deep soak waits for the next routine slot and replaces that routine,
instead of landing the day after a routine as a second full watering."""
from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import DEEP_SOAK_INTERVAL_BUFFER_SECONDS, ROUTINE_INTERVAL_BUFFER_SECONDS

from .test_irrigation_gates import _setup

DAY = 86400
RB = ROUTINE_INTERVAL_BUFFER_SECONDS
DB = DEEP_SOAK_INTERVAL_BUFFER_SECONDS


def test_waits_when_routine_ran_yesterday():
    assert calc.deep_soak_waits_for_routine(1 * DAY, 14 * DAY, 14, 4, RB, DB)


def test_runs_when_routine_is_due():
    assert not calc.deep_soak_waits_for_routine(4 * DAY, 14 * DAY, 14, 4, RB, DB)


def test_never_waits_more_than_one_routine_interval():
    # 14 days + 4 days past the last soak: stop waiting even if a routine ran yesterday.
    assert not calc.deep_soak_waits_for_routine(1 * DAY, 18 * DAY, 14, 4, RB, DB)
    assert calc.deep_soak_waits_for_routine(1 * DAY, 17 * DAY, 14, 4, RB, DB)


def test_a_zone_that_never_soaked_does_not_wait():
    assert not calc.deep_soak_waits_for_routine(1 * DAY, dt_util.utcnow().timestamp(), 14, 4, RB, DB)


async def _ready(hass, routine_days_ago, soak_days_ago):
    controller, _ = await _setup(hass)
    now = dt_util.utcnow().timestamp()
    controller.store.state.last_routine_ts = now - routine_days_ago * DAY
    controller.store.state.last_deep_soak_ts = now - soak_days_ago * DAY
    controller.store.state.last_significant_rain_ts = 0.0
    pulses = AsyncMock(return_value=True)
    controller._run_pulses = pulses
    return controller, pulses


@pytest.mark.asyncio
async def test_deep_soak_waits_after_a_recent_routine(hass):
    controller, pulses = await _ready(hass, routine_days_ago=1, soak_days_ago=14.1)
    await controller.run_deep_soak()
    pulses.assert_not_called()


@pytest.mark.asyncio
async def test_deep_soak_runs_when_routine_is_due_too(hass):
    controller, pulses = await _ready(hass, routine_days_ago=5, soak_days_ago=14.1)
    await controller.run_deep_soak()
    pulses.assert_called_once()


@pytest.mark.asyncio
async def test_manual_deep_soak_ignores_the_wait(hass):
    controller, pulses = await _ready(hass, routine_days_ago=1, soak_days_ago=14.1)
    await controller.run_deep_soak_now()
    pulses.assert_called_once()


@pytest.mark.asyncio
async def test_due_routine_runs_as_the_deep_soak_when_one_is_due(hass):
    controller, pulses = await _ready(hass, routine_days_ago=5, soak_days_ago=14.1)
    await controller.run_routine_irrigation()
    pulses.assert_called_once()
    assert pulses.call_args.kwargs["kind"] == "Deep Soak"


@pytest.mark.asyncio
async def test_routine_stays_a_routine_when_no_deep_soak_is_due(hass):
    controller, pulses = await _ready(hass, routine_days_ago=5, soak_days_ago=3)
    await controller.run_routine_irrigation()
    for call in pulses.call_args_list:
        assert call.kwargs["kind"] != "Deep Soak"


@pytest.mark.asyncio
async def test_routine_does_not_hand_over_when_the_soak_would_be_refused(hass):
    controller, pulses = await _ready(hass, routine_days_ago=5, soak_days_ago=14.1)
    # Deep soak blocked by dry-down (rain just now): the routine must not be skipped for it.
    controller.store.state.last_significant_rain_ts = dt_util.utcnow().timestamp()
    assert not controller._deep_soak_would_replace_routine(dt_util.utcnow().timestamp())
