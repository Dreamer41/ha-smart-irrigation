"""Runtime sensor-dropout scenarios: what happens when an already-configured
optional sensor stops reporting good data mid-season, as opposed to never
being configured at all (that graceful-degradation path is covered by
test_config_flow.py's minimal-setup test and controller.py's *_entity
properties returning None). A sensor going "unavailable"/"unknown" -- a
dead battery, a Zigbee dropout, a broken template -- must degrade the same
safe way as never having had it, and must recover automatically the moment
it starts reporting again; it must never crash a cycle or freeze on stale
data.
"""
import pytest

from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow.const import DOMAIN, EVENT_LOG

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, 999)
    hass.states.async_set(RAIN_COUNTER, 0)
    hass.states.async_set(OUTDOOR_TEMP, 25.0)
    await hass.async_block_till_done()


def _day_without_readings(controller):
    """A whole day passes with the temperature sensor offline: nothing is
    tracked, then the 23:59:50 shift records the day."""
    controller.store.state.today_peak_temp_c = None
    controller.store.state.today_min_temp_c = None
    controller._on_daily_shift(None)


@pytest.mark.asyncio
async def test_temp_sensor_dropout_keeps_last_real_days_then_uses_fallback(hass, fake_valve_services):
    """A sensor that drops out keeps its last REAL days until they age out
    of the 3-day window (a day without readings is recorded as none, never
    copied forward), then the Fallback / Manual Temperature slider takes
    over -- see controller.watering_temp. A dead sensor can therefore never
    hold a tier for more than 3 days, and a short blip changes nothing."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    hot = controller.number("hot_temp_threshold")

    controller.store.state.peak_temp_day_history_c = [35.0, 34.0, 36.0]
    hass.states.async_set(OUTDOOR_TEMP, "35.0")
    await hass.async_block_till_done()
    assert controller.watering_temp() == (35.0, "sensor")

    # Drops out: the recorded days are still real weather.
    for dead_state in ("unavailable", "unknown"):
        hass.states.async_set(OUTDOOR_TEMP, dead_state)
        await hass.async_block_till_done()
        assert controller.watering_temp() == (35.0, "last_known")

    # Each day without a reading pushes one real day out of the window.
    _day_without_readings(controller)
    assert controller.store.state.peak_temp_day_history_c == [None, 35.0, 34.0]
    assert controller.watering_temp() == (34.5, "last_known")
    _day_without_readings(controller)
    assert controller.watering_temp() == (35.0, "last_known")
    _day_without_readings(controller)
    # Nothing real left: the fallback (unset here -> the middle of the
    # cool/hot band, i.e. the normal tier).
    temp, source = controller.watering_temp()
    assert source == "fallback"
    assert controller.number("cool_temp_threshold") <= temp < hot
    assert controller.avg_peak_temp() is None

    # The fallback is a slider: set it for a heat wave.
    await controller.numbers["fallback_temp"].async_set_native_value(36.0)
    assert controller.watering_temp() == (36.0, "fallback")

    # Back online and a real day recorded: real data again.
    hass.states.async_set(OUTDOOR_TEMP, "29.0")
    await hass.async_block_till_done()
    controller._on_daily_shift(None)
    assert controller.watering_temp() == (29.0, "sensor")


@pytest.mark.asyncio
async def test_routine_irrigation_uses_last_known_then_fallback_when_temp_sensor_is_dead(hass, fake_valve_services):
    """End-to-end: what a real routine run calculates with a dead sensor.
    _run_pulses is mocked out (like test_irrigation_gates.py does) purely so
    this test doesn't have to wait through real multi-minute pulses --
    everything up to and including the tier/target calculation runs for
    real."""
    from unittest.mock import AsyncMock

    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    await hass.async_block_till_done()

    async def run():
        spy = AsyncMock(return_value=True)
        controller._run_pulses = spy
        controller.store.state.last_routine_ts = None
        await controller.run_routine_irrigation()
        await hass.async_block_till_done()
        spy.assert_called_once()
        return spy.call_args.kwargs["target_mm_for_log"]

    # Hot days still on record: hot tier (45 mm/week over 3 days).
    controller.store.state.peak_temp_day_history_c = [35.0, 34.0, 36.0]
    assert await run() == pytest.approx(45.0 / 7 * 3, abs=0.05)

    # No real day left: the fallback -- unset, so the normal tier
    # (35 mm/week over 4 days = 20 mm).
    controller.store.state.peak_temp_day_history_c = [None, None, None]
    assert await run() == pytest.approx(20.0)

    # Fallback set below the cool threshold: cool tier (25 mm/week, 4 days).
    await controller.numbers["fallback_temp"].async_set_native_value(20.0)
    assert await run() == pytest.approx(25.0 / 7 * 4, abs=0.05)


@pytest.mark.asyncio
async def test_zone_without_temp_sensor_follows_the_manual_temperature(hass, fake_valve_services):
    """No temperature sensor at all: the Fallback / Manual Temperature is
    how a person tells the zone about a hot or cool spell."""
    await _seed(hass)
    entry = make_entry(hass, outdoor_temp_entity=None)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.outdoor_temp_entity is None

    temp, source = controller.watering_temp()
    assert source == "manual"
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_mm")  # normal until told

    await controller.numbers["fallback_temp"].async_set_native_value(35.0)
    assert controller.watering_temp() == (35.0, "manual")
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_hot_mm")


@pytest.mark.asyncio
async def test_rain_counter_dropout_readings_are_dropped_not_recorded_as_zero(hass, fake_valve_services):
    """A rain-gauge tip counter reporting "unavailable"/"unknown" must be
    silently ignored (see controller._sync_rain_from_counter_state's
    float() try/except) rather than being recorded as a real 0.0 reading,
    which would corrupt the rolling window with a fake "no more rain"
    sample and could even show rainfall going backwards."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(RAIN_COUNTER, "40")  # 40 tips recorded so far
    await hass.async_block_till_done()
    before = controller.rain_windows()["24h"]
    assert before > 0

    # The gauge drops out.
    for dead_state in ("unavailable", "unknown", ""):
        hass.states.async_set(RAIN_COUNTER, dead_state)
        await hass.async_block_till_done()

    # No exception, and the last good reading is still what the windows
    # reflect -- a dropout must never look like "it stopped raining".
    after = controller.rain_windows()["24h"]
    assert after == before


@pytest.mark.asyncio
async def test_pump_power_dropout_during_pulse_warns_but_still_completes(hass, fake_valve_services, monkeypatch):
    """A pump-power sensor that's configured but currently unreadable must
    behave like a real low-power reading (0.0, see controller._pump_watts)
    -- it warns, exactly as a genuinely underpowered pump would, but still
    lets the pulse run to completion rather than crashing or hanging."""
    # The real 45s wait_for_pump_watts timeout would make this test take
    # 45 real seconds; shrink it the same way fast_startup_grace shrinks
    # STARTUP_GRACE_SECONDS.
    monkeypatch.setattr(controller_module, "PUMP_POWER_WAIT_TIMEOUT_SECONDS", 0.05)

    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(PUMP, "unavailable")
    await hass.async_block_till_done()
    assert controller.pump_power_entity  # still configured, just unreadable right now

    events = []
    unsub = hass.bus.async_listen(EVENT_LOG, lambda e: events.append(e.data))
    valve_events = []
    unsub_valve = hass.bus.async_listen(
        "state_changed",
        lambda e: valve_events.append(e.data["new_state"].state) if e.data.get("entity_id") == VALVE else None,
    )
    try:
        await controller.test_pulse(1)
        await hass.async_block_till_done()
    finally:
        unsub()
        unsub_valve()

    assert any(e["event_type"] == "Low Pump Power Audit" for e in events)
    # The pulse still ran the valve open and closed -- a dead pump-power
    # sensor degrades to a warning, it never blocks the actual watering.
    assert "on" in valve_events and "off" in valve_events


@pytest.mark.asyncio
async def test_flow_meter_dropout_skips_no_flow_check_instead_of_false_alarming(hass, fake_valve_services):
    """A configured-but-currently-unreadable flow meter must not be treated
    as "definitely zero flow" -- controller._flow_meter_reading() returns
    None (not 0.0) so _run_pulses can tell "no data" apart from "reads
    zero", and the No-Flow-Detected check is skipped entirely rather than
    firing a false alarm every single cycle."""
    await _seed(hass)
    entry = make_entry(hass, flow_meter_entity="sensor.flow_meter_liters")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set("sensor.flow_meter_liters", "unavailable")
    await hass.async_block_till_done()

    events = []
    unsub = hass.bus.async_listen(EVENT_LOG, lambda e: events.append(e.data))
    try:
        await controller.test_pulse(1)
        await hass.async_block_till_done()
    finally:
        unsub()

    assert not any(e["event_type"] == "No Flow Detected" for e in events)
    assert controller.store.state.last_cycle_water_liters is None
