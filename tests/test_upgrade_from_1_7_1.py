"""Upgrading from 1.7.1: a zone saved before "watered by the rain" (no rain
credit fields) keeps its watering history, nothing is marked without rain, and
the new records start empty."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow.const import DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

NEW_IN_1_7_2 = {"rain_credit_spent_mm", "rain_credit_spent_ts"}


@pytest.mark.asyncio
async def test_a_1_7_1_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = {k: v for k, v in asdict(IrrigationState()).items() if k not in NEW_IN_1_7_2}
    now = 1_790_000_000.0
    old.update(last_routine_ts=now - 86400, last_deep_soak_ts=now - 3 * 86400, rain_day_history_mm=[0.0] * 10)
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "10"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    state = zone.store.state
    assert state.last_routine_ts == now - 86400 and state.last_deep_soak_ts == now - 3 * 86400  # nothing reset
    assert state.rain_credit_spent_mm == 0.0 and state.rain_credit_spent_ts is None  # the new records start empty
    assert zone.rain_offset_mm() == 0.0
    await zone._on_rain_credit_check()  # no rain on record: nothing is marked
    assert state.last_routine_ts == now - 86400 and state.last_deep_soak_ts == now - 3 * 86400
