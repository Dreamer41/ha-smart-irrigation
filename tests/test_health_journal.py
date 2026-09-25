"""ZoneFlowHealthSelect + ZoneFlowHealthNotesText: a pure human journal,
with zero effect on watering logic -- see select.py/text.py module
docstrings. These tests confirm the entities exist, default sensibly,
persist a change, and (critically) that setting them doesn't perturb any
watering-decision state.
"""
import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "0")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_health_select_defaults_to_good_and_is_settable(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = next(s.entity_id for s in hass.states.async_all("select") if "health" in s.entity_id)
    assert hass.states.get(entity_id).state == "good"

    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "poor"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "poor"

    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.store.state.health_status == "poor"


@pytest.mark.asyncio
async def test_health_notes_defaults_empty_and_persists_a_value(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = next(s.entity_id for s in hass.states.async_all("text") if "health_notes" in s.entity_id)
    assert hass.states.get(entity_id).state == ""

    await hass.services.async_call(
        "text", "set_value", {"entity_id": entity_id, "value": "yellowing lower leaves, watching it"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "yellowing lower leaves, watching it"

    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.store.state.health_notes == "yellowing lower leaves, watching it"


@pytest.mark.asyncio
async def test_health_journal_never_affects_watering_gates(hass, fake_valve_services):
    """The whole point of a pure journal entity: changing it must not
    perturb anything the run-gates actually look at."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    before = (
        controller.store.state.last_routine_ts,
        controller.store.state.last_deep_soak_ts,
        controller.store.state.lock_on,
    )

    controller.store.state.health_status = "sick"
    controller.store.state.health_notes = "wilting badly"
    await controller.store.async_save()

    after = (
        controller.store.state.last_routine_ts,
        controller.store.state.last_deep_soak_ts,
        controller.store.state.lock_on,
    )
    assert before == after


@pytest.mark.asyncio
async def test_fertilizing_interval_defaults_to_three_months_and_is_settable(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = next(s.entity_id for s in hass.states.async_all("select") if "fertilizing" in s.entity_id)
    state = hass.states.get(entity_id)
    assert state.state == "3"
    assert state.attributes["options"] == [str(m) for m in range(1, 13)]

    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "6"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "6"
    assert hass.data[DOMAIN][entry.entry_id].store.state.fertilizing_interval_months == "6"


@pytest.mark.asyncio
async def test_last_fertilizing_starts_unset_and_persists_a_date(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = next(s.entity_id for s in hass.states.async_all("datetime") if "fertilizing" in s.entity_id)
    assert hass.states.get(entity_id).state == "unknown"

    await hass.services.async_call(
        "datetime", "set_value", {"entity_id": entity_id, "datetime": "2026-09-01 08:00:00"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state not in ("unknown", "unavailable")
    assert hass.data[DOMAIN][entry.entry_id].store.state.last_fertilizing_ts is not None


@pytest.mark.asyncio
async def test_fertilizing_fields_never_affect_watering_gates(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    before = (
        controller.store.state.last_routine_ts,
        controller.store.state.last_deep_soak_ts,
        controller.store.state.lock_on,
        controller.number("routine_drydown_days"),
    )
    controller.store.state.last_fertilizing_ts = 1_700_000_000.0
    controller.store.state.fertilizing_interval_months = "12"
    await controller.store.async_save()
    after = (
        controller.store.state.last_routine_ts,
        controller.store.state.last_deep_soak_ts,
        controller.store.state.lock_on,
        controller.number("routine_drydown_days"),
    )
    assert before == after
