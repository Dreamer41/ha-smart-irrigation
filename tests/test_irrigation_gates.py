"""Does run_deep_soak / run_routine_irrigation correctly decide whether to
water at all, before ever touching the valve?

These gates all return early, so they're fast to test directly (no real
multi-minute pulses involved) -- and getting them right matters just as
much as the pulse mechanics: this is what stops the integration watering
on a schedule when it shouldn't (already locked, too soon, still wet from
rain, or a miscalibrated runtime that would way overshoot).
"""
from unittest.mock import AsyncMock

import pytest

from custom_components.zoneflow.const import CONF_DEEP_SOAK_ENABLED, DOMAIN

from .test_smoke_setup import RAIN_COUNTER, _seed_source_entities, make_entry


async def _setup(hass, **entry_overrides):
    await _seed_source_entities(hass)
    entry = make_entry(hass, **entry_overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    # Spy on _run_pulses on every gate test: if a gate is supposed to skip
    # the run, the valve must never even be asked to move.
    spy = AsyncMock(wraps=controller._run_pulses)
    controller._run_pulses = spy
    return controller, spy


async def _set_number(hass, friendly_name_suffix: str, value: float) -> None:
    entity_id = None
    for state in hass.states.async_all("number"):
        if state.attributes.get("friendly_name", "").endswith(friendly_name_suffix):
            entity_id = state.entity_id
            break
    assert entity_id, f"could not find a number entity ending in {friendly_name_suffix!r}"
    await hass.services.async_call("number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True)


@pytest.mark.asyncio
async def test_deep_soak_skipped_when_already_locked(hass):
    controller, spy = await _setup(hass)
    await controller._set_lock(True)

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_deep_soak_skipped_when_not_yet_due(hass):
    controller, spy = await _setup(hass)
    import homeassistant.util.dt as dt_util

    # Just watered a moment ago -- nowhere near the 14-day interval.
    controller.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp()

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_deep_soak_skipped_entirely_when_turned_off_for_this_zone(hass):
    """Some crops/setups don't want the deep-soak cycle at all (see
    const.py's CONF_DEEP_SOAK_ENABLED) -- with it off, run_deep_soak() must
    never touch the valve, even though every other gate (due, dry-down,
    rain ceiling) would otherwise allow it."""
    controller, spy = await _setup(hass, **{CONF_DEEP_SOAK_ENABLED: False})
    # Nothing else is blocking a run -- never watered, no recent rain -- so
    # this isolates the deep_soak_enabled gate specifically.
    controller.store.state.last_deep_soak_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    spy.assert_not_called()

    # The manual "Run Deep Soak Now" button hits the exact same code path,
    # so it must no-op too rather than bypassing the zone's own setting.
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_deep_soak_skipped_when_subsoil_still_wet_from_rain(hass):
    controller, spy = await _setup(hass)
    import homeassistant.util.dt as dt_util

    # Significant rain moments ago -- default deep-soak dry-down holdoff is
    # 8 days, so this should still block a deep soak.
    controller.store.state.last_significant_rain_ts = dt_util.utcnow().timestamp()

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_deep_soak_cancelled_when_calculated_runtime_exceeds_safety_cap(hass):
    controller, spy = await _setup(hass)

    # Max target (40mm) at min flow rate (0.05mm/min) -> 800min total runtime,
    # far past the default 124min safety cap.
    await _set_number(hass, "Deep Soak Target Depth", 40.0)
    await _set_number(hass, "Emitter Flow Rate Calibration", 0.05)

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    spy.assert_not_called()
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_deep_soak_cancelled_by_rain_in_the_last_30_minutes(hass):
    controller, spy = await _setup(hass)

    # ~10mm just now: above the 3mm/30min pre-irrigation cancel threshold,
    # but comfortably under the 40mm/14d deep-soak rain ceiling, so this
    # exercises the pre-irrigation check specifically (not the rain-ceiling
    # gate above it).
    hass.states.async_set(RAIN_COUNTER, "34")
    await hass.async_block_till_done()

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    spy.assert_not_called()
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_routine_skipped_when_already_locked(hass):
    controller, spy = await _setup(hass)
    await controller._set_lock(True)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_routine_skipped_when_not_yet_due(hass):
    controller, spy = await _setup(hass)
    import homeassistant.util.dt as dt_util

    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp()

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_routine_cancelled_when_calculated_runtime_exceeds_safety_cap(hass):
    controller, spy = await _setup(hass)

    # Max normal weekly target combined with min flow rate massively
    # overshoots the default 103min routine safety cap.
    await _set_number(hass, "Routine Normal Weekly Target", 60.0)
    await _set_number(hass, "Emitter Flow Rate Calibration", 0.05)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_routine_cancelled_by_rain_in_the_last_30_minutes(hass):
    controller, spy = await _setup(hass)

    hass.states.async_set(RAIN_COUNTER, "34")  # ~10mm just now
    await hass.async_block_till_done()

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()
    assert controller.store.state.lock_on is False
