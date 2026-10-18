"""The stale-lock watchdog (lock ON for 180 minutes) must not clear the lock of a watering that
is still running: Water now in pulses, or many pulses with long soaks on clay, can take longer."""
from __future__ import annotations

import asyncio

import pytest

from .test_scenarios_cycles import _zone


@pytest.mark.asyncio
async def test_a_running_watering_is_not_a_stale_lock(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, events = await _zone(hass, monkeypatch, tmp_path)
    state = controller.store.state
    state.lock_on = True
    running = asyncio.ensure_future(asyncio.sleep(3600))
    controller._runs.add(running)
    try:
        controller._on_stale_lock(None)
        await hass.async_block_till_done()
        assert state.lock_on is True and "Stale Lock Watchdog Fired" not in events  # looked again later
        assert controller._lock_stale_cancel is not None
    finally:
        controller._runs.discard(running)
        running.cancel()

    controller._on_stale_lock(None)  # nothing running any more: this is a stuck lock
    await hass.async_block_till_done()
    assert state.lock_on is False and "Stale Lock Watchdog Fired" in events
