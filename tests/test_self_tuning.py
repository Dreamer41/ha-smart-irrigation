"""Self-tuning intervals (controller.py's _register_self_tune_signal) --
see const.py's SELF_TUNE_* comment. A rolling streak of manual routine
presses that land on the plain time-based model's "not yet due" verdict
shrinks routine_drydown_days; a rolling streak of Snooze Today presses
extends it; either resets the other. The manual press never bypasses any
gate -- when it's not due, it's still a no-op (same as before this feature
existed), just one that now also advances the streak.
"""
from unittest.mock import AsyncMock

import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

SOIL_MOISTURE = "sensor.soil_moisture_zone1"


async def _seed(hass, moisture: str | None = None):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    if moisture is not None:
        hass.states.async_set(SOIL_MOISTURE, moisture)
    await hass.async_block_till_done()


async def _setup(hass, **overrides):
    entry = make_entry(hass, **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _make_not_yet_due(controller):
    """last_routine_ts = now, so the plain time-based model clearly does
    NOT think a routine cycle is due yet."""
    import homeassistant.util.dt as dt_util

    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp()
    controller.store.state.last_significant_rain_ts = 0.0


def _make_due(controller):
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0


@pytest.mark.asyncio
async def test_three_early_manual_presses_shrink_drydown_and_reset_streak(hass, fake_valve_services):
    """Each press is a no-op (nothing was due), but three of them in a row
    is still the "early" signal -- the person pressing the button when the
    model says "not yet" is the signal, whether or not anything waters."""
    await _seed(hass)
    controller = await _setup(hass)
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    starting = controller.number("routine_drydown_days")
    for _ in range(3):
        _make_not_yet_due(controller)
        await controller.run_routine_irrigation(manual=True)
        await hass.async_block_till_done()

    spy.assert_not_called()
    assert controller.number("routine_drydown_days") == starting - 0.5
    assert controller.store.state.self_tune_early_streak == 0


@pytest.mark.asyncio
async def test_three_snoozes_in_a_row_extend_drydown_and_reset_streak(hass, fake_valve_services):
    await _seed(hass)
    controller = await _setup(hass)

    starting = controller.number("routine_drydown_days")
    for _ in range(3):
        controller.store.state.snooze_date_iso = None
        await controller.snooze_today()
        await hass.async_block_till_done()

    assert controller.number("routine_drydown_days") == starting + 0.5
    assert controller.store.state.self_tune_skip_streak == 0


@pytest.mark.asyncio
async def test_early_then_skip_resets_the_early_streak_without_a_nudge(hass, fake_valve_services):
    await _seed(hass)
    controller = await _setup(hass)
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    starting = controller.number("routine_drydown_days")
    _make_not_yet_due(controller)
    await controller.run_routine_irrigation(manual=True)
    await hass.async_block_till_done()
    assert controller.store.state.self_tune_early_streak == 1

    await controller.snooze_today()
    await hass.async_block_till_done()

    assert controller.store.state.self_tune_early_streak == 0
    assert controller.store.state.self_tune_skip_streak == 1
    assert controller.number("routine_drydown_days") == starting


@pytest.mark.asyncio
async def test_self_tune_clamps_at_the_number_entitys_minimum(hass, fake_valve_services):
    await _seed(hass)
    controller = await _setup(hass)
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    # NUMBER_DEFS min for routine_drydown_days is 1.0 -- start right at the
    # floor so a shrink nudge has nowhere to go.
    await controller.numbers["routine_drydown_days"].async_set_native_value(1.0)

    for _ in range(3):
        _make_not_yet_due(controller)
        await controller.run_routine_irrigation(manual=True)
        await hass.async_block_till_done()

    assert controller.number("routine_drydown_days") == 1.0


@pytest.mark.asyncio
async def test_a_manual_press_blocked_by_the_lock_does_not_count_toward_the_streak(hass, fake_valve_services):
    """A manual press that never even reaches the interval-due check (e.g.
    the mutex lock is already held) must not silently advance the streak --
    only a press that actually lands on the model's "not yet due" verdict
    counts as an "early" signal."""
    await _seed(hass)
    controller = await _setup(hass)
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    _make_not_yet_due(controller)
    controller.store.state.lock_on = True
    await controller.run_routine_irrigation(manual=True)
    await hass.async_block_till_done()

    spy.assert_not_called()
    assert controller.store.state.self_tune_early_streak == 0


@pytest.mark.asyncio
async def test_a_due_manual_run_does_not_count_as_early(hass, fake_valve_services):
    """Pressing the button when a run genuinely was already due must not
    feed the self-tune signal -- only a run the model didn't yet expect
    counts as "early"."""
    await _seed(hass)
    controller = await _setup(hass)
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    _make_due(controller)
    await controller.run_routine_irrigation(manual=True)
    await hass.async_block_till_done()

    spy.assert_called_once()
    assert controller.store.state.self_tune_early_streak == 0


@pytest.mark.asyncio
async def test_a_scheduled_not_due_run_never_touches_the_streak(hass, fake_valve_services):
    """The exact same "not yet due" no-op, but WITHOUT manual=True (i.e.
    the 05:30 scheduled trigger) -- the streak must stay untouched, since
    this feature is about manual override behavior, not the model
    correctly declining to run on its own schedule."""
    await _seed(hass)
    controller = await _setup(hass)
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    _make_not_yet_due(controller)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()
    assert controller.store.state.self_tune_early_streak == 0


@pytest.mark.asyncio
async def test_soil_moisture_forcing_an_early_manual_run_through_also_counts(hass, fake_valve_services):
    """The rarer path: a configured soil-moisture sensor is dry enough to
    force the cycle to actually run despite the plain interval saying not
    due -- if that was also a manual press, it's still the same "early"
    signal, from the completion side of the gate instead of the no-op
    side."""
    await _seed(hass, moisture="10")  # well below the 20% default dry threshold
    controller = await _setup(hass, soil_moisture_entity=SOIL_MOISTURE)
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    _make_not_yet_due(controller)
    await controller.run_routine_irrigation(manual=True)
    await hass.async_block_till_done()

    spy.assert_called_once()
    assert controller.store.state.self_tune_early_streak == 1
