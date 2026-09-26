"""End-to-end: an optional soil-moisture sensor becomes the direct decider
of routine irrigation, ahead of the plain time-interval estimate -- see
calculations.routine_due_with_soil_moisture (unit-tested in
test_calculations.py) and controller.run_routine_irrigation's gate. These
tests exercise the real config-entry/controller wiring, including the
dropout fallback.
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


async def _make_due_but_not_yet_by_interval(controller, hass):
    """last_routine_ts = now (interval clearly NOT elapsed) so any run
    that still happens must be because soil moisture forced it, not the
    time interval."""
    import homeassistant.util.dt as dt_util

    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp()
    controller.store.state.last_significant_rain_ts = 0.0
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_dry_soil_moisture_forces_a_run_even_though_interval_isnt_due(hass, fake_valve_services):
    await _seed(hass, moisture="10")  # well below the 20% default dry threshold
    entry = make_entry(hass, soil_moisture_entity=SOIL_MOISTURE)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    await _make_due_but_not_yet_by_interval(controller, hass)

    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_called_once()


@pytest.mark.asyncio
async def test_wet_soil_moisture_skips_even_though_interval_says_overdue(hass, fake_valve_services):
    await _seed(hass, moisture="80")  # well above the 60% default wet threshold
    entry = make_entry(hass, soil_moisture_entity=SOIL_MOISTURE)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    # Overdue by the plain time interval -- last run 30 days ago.
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0

    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_soil_moisture_dropout_falls_back_to_the_modeled_interval(hass, fake_valve_services):
    """A configured-but-currently-unreadable soil-moisture sensor must
    degrade to "no override" -- same dropout pattern as temp/rain/pump --
    not to a numeric guess in either direction."""
    await _seed(hass, moisture="unavailable")
    entry = make_entry(hass, soil_moisture_entity=SOIL_MOISTURE)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    assert await controller._soil_moisture_pct() is None

    # Overdue by the plain interval -- should proceed exactly as if no
    # soil-moisture sensor were configured at all.
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0

    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_called_once()


@pytest.mark.asyncio
async def test_unconfigured_soil_moisture_behaves_exactly_as_before(hass, fake_valve_services):
    """No soil_moisture_entity in the config at all -- the feature must be
    fully inert, not just gracefully degraded."""
    await _seed(hass)
    entry = make_entry(hass)  # no soil_moisture_entity
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    assert controller.soil_moisture_entity is None
    assert await controller._soil_moisture_pct() is None


async def _probe_zone(hass, moisture):
    await _seed(hass, moisture=moisture)
    entry = make_entry(hass, soil_moisture_entity=SOIL_MOISTURE)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    controller._run_pulses = AsyncMock(return_value=True)
    return controller


async def _overdue_routine(controller, hass):
    """A routine check with the plain interval long overdue."""
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0
    controller._run_pulses.reset_mock()
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    return controller._run_pulses.called


@pytest.mark.asyncio
@pytest.mark.parametrize("reading", ["150", "-5"])
async def test_impossible_moisture_reading_is_ignored(hass, fake_valve_services, reading):
    """150% or -5% is a broken probe or template, not soil: the schedule
    decides, and the status says why."""
    controller = await _probe_zone(hass, reading)
    assert controller.soil_moisture_status() == "implausible"
    assert controller.soil_moisture_reading() is None
    assert controller.soil_moisture_raw() == float(reading)
    assert await _overdue_routine(controller, hass)  # 150 would otherwise have read as "wet, skip"


@pytest.mark.asyncio
async def test_frozen_dry_reading_stops_forcing_runs(hass, fake_valve_services, monkeypatch):
    """A dry reading that hasn't been reported for SOIL_MOISTURE_STALE_SECONDS
    is ignored: a frozen "dry" must not force watering at every scheduled
    time. A new report makes it count again."""
    import asyncio

    from custom_components.zoneflow import controller as controller_module

    controller = await _probe_zone(hass, "10")
    await _make_due_but_not_yet_by_interval(controller, hass)
    assert controller.soil_moisture_status() == "dry"

    monkeypatch.setattr(controller_module, "SOIL_MOISTURE_STALE_SECONDS", 0.05)
    await asyncio.sleep(0.1)
    assert controller.soil_moisture_status() == "stale"
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    controller._run_pulses.assert_not_called()  # not due by schedule, dry reading ignored

    hass.states.async_set(SOIL_MOISTURE, "10", force_update=True)
    await hass.async_block_till_done()
    assert controller.soil_moisture_status() == "dry"


@pytest.mark.asyncio
async def test_frozen_wet_reading_is_respected_until_the_hold_limit(hass, fake_valve_services, monkeypatch):
    """MQTT/Zigbee2MQTT and template sensors never re-report an unchanged
    value, and a probe in soaked soil sits pinned at one wet value for days:
    a stale WET reading is still respected. But once wet readings have held
    a due run back for 2 routine intervals without the probe reporting, the
    schedule waters once (with an alert) and the hold starts over."""
    import asyncio

    import homeassistant.util.dt as dt_util

    from custom_components.zoneflow import controller as controller_module
    from custom_components.zoneflow.const import EVENT_LOG

    controller = await _probe_zone(hass, "100")
    monkeypatch.setattr(controller_module, "SOIL_MOISTURE_STALE_SECONDS", 0.05)
    await asyncio.sleep(0.1)
    assert controller.soil_moisture_status() == "wet"  # stale, but wet: respected
    assert not await _overdue_routine(controller, hass)
    assert controller.store.state.wet_hold_since_ts is not None

    events = []
    unsub = hass.bus.async_listen(EVENT_LOG, lambda e: events.append(e.data))
    try:
        controller.store.state.wet_hold_since_ts = dt_util.utcnow().timestamp() - 9 * 86400
        assert controller.soil_moisture_status() == "stale"
        assert await _overdue_routine(controller, hass)  # the schedule waters
        alerts = [e for e in events if e["event_type"] == "Soil Probe Check"]
        assert len(alerts) == 1
        assert controller.store.state.wet_hold_since_ts is None
    finally:
        unsub()

    # Next time it's due, the pinned wet reading is respected again.
    controller.store.state.last_routine_ts = 0.0
    assert controller.soil_moisture_status() == "wet"


@pytest.mark.asyncio
async def test_long_wet_hold_sends_one_probe_check_alert(hass, fake_valve_services):
    """Wet soil can legitimately hold watering back for days after heavy
    rain, so the probe is still followed -- but after twice the routine
    interval, one alert asks the person to check it. It resets once the
    soil reads anything but wet."""
    import homeassistant.util.dt as dt_util

    from custom_components.zoneflow.const import EVENT_LOG

    controller = await _probe_zone(hass, "80")
    events = []
    unsub = hass.bus.async_listen(EVENT_LOG, lambda e: events.append(e.data["event_type"]))
    try:
        assert not await _overdue_routine(controller, hass)
        since = controller.store.state.wet_hold_since_ts
        assert since is not None
        assert "Soil Probe Check" not in events

        # 7 days on a 4-day interval: still under the 8-day alert point.
        controller.store.state.wet_hold_since_ts = dt_util.utcnow().timestamp() - 7 * 86400
        assert not await _overdue_routine(controller, hass)
        assert "Soil Probe Check" not in events

        # 9 days: one alert, and only one.
        controller.store.state.wet_hold_since_ts = dt_util.utcnow().timestamp() - 9 * 86400
        assert not await _overdue_routine(controller, hass)
        assert not await _overdue_routine(controller, hass)
        assert events.count("Soil Probe Check") == 1
        assert controller.store.state.wet_hold_alerted is True

        # The soil dries into range: the hold ends (and the overdue run goes ahead).
        hass.states.async_set(SOIL_MOISTURE, "40")
        await hass.async_block_till_done()
        assert await _overdue_routine(controller, hass)
        assert controller.store.state.wet_hold_since_ts is None
        assert controller.store.state.wet_hold_alerted is False
    finally:
        unsub()


@pytest.mark.asyncio
async def test_stale_or_implausible_probe_doesnt_trip_deficit_dry_guard_or_estimate(hass, fake_valve_services):
    """Everything that reads moisture uses the same usable-reading check:
    an impossible 0-ish reading can't pull the next-run estimate forward."""
    controller = await _probe_zone(hass, "-3")
    controller.store.state.last_routine_ts = 1.0
    assert controller.routine_next_estimate()[1] == "schedule"


@pytest.mark.asyncio
async def test_ending_a_wet_hold_is_saved(hass, fake_valve_services):
    """Otherwise a restart could bring an old hold back and alert early."""
    import homeassistant.util.dt as dt_util

    controller = await _probe_zone(hass, "40")
    controller.store.state.wet_hold_since_ts = dt_util.utcnow().timestamp() - 3 * 86400
    await controller.store.async_save()
    await _make_due_but_not_yet_by_interval(controller, hass)
    await controller.run_routine_irrigation()  # in range, not due: ends the hold
    await hass.async_block_till_done()
    entry = controller.entry
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].store.state.wet_hold_since_ts is None


@pytest.mark.asyncio
async def test_frozen_wet_limit_survives_a_blocked_run(hass, fake_valve_services, monkeypatch):
    """Regression: the hold used to be cleared (and the alert sent) before
    the rain dry-down / forecast gates, so a blocked run restarted the
    8-day wait. Now the limit stands until watering actually starts, and
    the frozen alert goes out once."""
    import asyncio

    import homeassistant.util.dt as dt_util

    from custom_components.zoneflow import controller as controller_module
    from custom_components.zoneflow.const import EVENT_LOG

    controller = await _probe_zone(hass, "100")
    monkeypatch.setattr(controller_module, "SOIL_MOISTURE_STALE_SECONDS", 0.05)
    await asyncio.sleep(0.1)
    now = dt_util.utcnow().timestamp()
    controller.store.state.wet_hold_since_ts = now - 9 * 86400
    events = []
    unsub = hass.bus.async_listen(EVENT_LOG, lambda e: events.append(e.data["event_type"]))
    try:
        # Heavy rain yesterday: the dry-down blocks this run.
        controller.store.state.last_routine_ts = 0.0
        controller.store.state.last_significant_rain_ts = now - 1 * 86400
        await controller.run_routine_irrigation()
        await hass.async_block_till_done()
        controller._run_pulses.assert_not_called()
        assert controller.store.state.wet_hold_since_ts == pytest.approx(now - 9 * 86400)
        assert controller.soil_moisture_status() == "stale"

        await controller.run_routine_irrigation()  # next day, still blocked
        await hass.async_block_till_done()
        assert events.count("Soil Probe Check") == 1

        # Dry-down over: it waters, and the hold ends.
        assert await _overdue_routine(controller, hass)
        assert controller.store.state.wet_hold_since_ts is None
        assert events.count("Soil Probe Check") == 1
    finally:
        unsub()


@pytest.mark.asyncio
async def test_stale_in_range_reading_during_a_hold_sends_no_frozen_alert(hass, fake_valve_services, monkeypatch):
    """The frozen-probe alert is only for a wet reading."""
    import asyncio

    import homeassistant.util.dt as dt_util

    from custom_components.zoneflow import controller as controller_module
    from custom_components.zoneflow.const import EVENT_LOG

    controller = await _probe_zone(hass, "40")
    monkeypatch.setattr(controller_module, "SOIL_MOISTURE_STALE_SECONDS", 0.05)
    await asyncio.sleep(0.1)
    controller.store.state.wet_hold_since_ts = dt_util.utcnow().timestamp() - 9 * 86400
    events = []
    unsub = hass.bus.async_listen(EVENT_LOG, lambda e: events.append(e.data["event_type"]))
    try:
        assert controller.soil_moisture_status() == "stale"
        assert await _overdue_routine(controller, hass)  # the schedule decides
        assert "Soil Probe Check" not in events
        assert controller.store.state.wet_hold_since_ts is None
    finally:
        unsub()
