"""Setup-time (or any-time-after) seeding of "when did this last happen" so
a newly-added zone for an already-established plant doesn't look overdue
and fire on the very next schedule. Covers both directions: setting a
datetime entity actually changes the gating math, and it survives exactly
like any other persisted state.
"""
import pytest
import homeassistant.util.dt as dt_util

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import PUMP, RAIN_COUNTER, VALVE, OUTDOOR_TEMP, make_entry


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "0")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_datetime_entities_are_created_and_start_unknown(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for suffix in ("last_routine_ts", "last_deep_soak_ts", "last_significant_rain_ts"):
        entity_id = f"datetime.test_zone_{suffix.removesuffix('_ts')}"
        # Entity IDs are derived from the friendly name by HA, not literally
        # this string -- fall back to a search if the exact slug differs.
        matches = [s for s in hass.states.async_all("datetime") if s.entity_id.startswith("datetime.test_zone")]
        assert len(matches) == 3
        for state in matches:
            assert state.state == "unknown"


@pytest.mark.asyncio
async def test_setting_last_routine_seeds_the_controller_state_and_persists(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    entity_id = next(
        s.entity_id
        for s in hass.states.async_all("datetime")
        if s.entity_id.startswith("datetime.test_zone") and "routine" in s.entity_id
    )
    five_days_ago = dt_util.utcnow() - dt_util.dt.timedelta(days=5)
    await hass.services.async_call(
        "datetime", "set_value", {"entity_id": entity_id, "datetime": five_days_ago.isoformat()}, blocking=True
    )
    await hass.async_block_till_done()

    assert controller.store.state.last_routine_ts is not None
    assert abs(controller.store.state.last_routine_ts - five_days_ago.timestamp()) < 2

    # And the datetime entity now reflects it back, instead of "unknown".
    state = hass.states.get(entity_id)
    assert state.state != "unknown"


@pytest.mark.asyncio
async def test_seeding_last_deep_soak_prevents_an_immediate_unwanted_run(hass, fake_valve_services):
    """The whole point: a fresh zone for an already-recently-deep-soaked
    plant shouldn't immediately deep-soak again just because it has no
    history. Seed last_deep_soak_ts to "just now" and confirm run_deep_soak
    correctly treats it as not due."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    entity_id = next(
        s.entity_id
        for s in hass.states.async_all("datetime")
        if s.entity_id.startswith("datetime.test_zone") and "deep_soak" in s.entity_id
    )
    now = dt_util.utcnow()
    await hass.services.async_call(
        "datetime", "set_value", {"entity_id": entity_id, "datetime": now.isoformat()}, blocking=True
    )
    await hass.async_block_till_done()

    valve_events = []
    unsub = hass.bus.async_listen(
        "state_changed",
        lambda event: valve_events.append(event.data["new_state"].state)
        if event.data.get("entity_id") == VALVE
        else None,
    )
    try:
        await controller.run_deep_soak()
        await hass.async_block_till_done()
    finally:
        unsub()

    # Freshly "deep soaked" -- the 14-day interval isn't up, so no pulses ran.
    assert "on" not in valve_events
