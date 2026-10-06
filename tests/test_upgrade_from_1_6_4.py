"""Upgrading from 1.6.4: a zone saved before the rain sensor types and the
water-use record (none of those fields) keeps its rain history and settings,
reads its rain sensor as a tip counter as before, and starts the new records
empty -- no reset, no jump."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow.const import DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

NEW_IN_1_6_5 = {
    "rain_source_signature", "rain_rate_last_mm_h", "rain_rate_last_ts",
    "last_cycle_liters", "water_ledger", "rain_samples_mm_per_tip",
}


@pytest.mark.asyncio
async def test_a_1_6_4_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = {k: v for k, v in asdict(IrrigationState()).items() if k not in NEW_IN_1_6_5}
    now = 1_790_000_000.0
    old.update(
        last_routine_ts=now - 86400,
        rain_counter_total_tips=449.0,
        rain_counter_last_tips=449.0,
        rain_samples=[[now - 7 * 86400, 100.0], [now - 3600, 134.7]],  # 34.7 mm over the window
        rain_midnight_baseline_mm=134.7,
    )
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "449"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    state = zone.store.state
    # Read as a tip counter, exactly as before; nothing was reset.
    assert zone.rain_source_type == "tips"
    assert state.rain_samples[0][1] == 100.0 and len(state.rain_samples) >= 2
    assert state.rain_counter_total_tips == 449.0
    assert state.rain_source_signature == f"tips|{RAIN_COUNTER}"
    # The new records start empty and the new sensors have nothing to say yet.
    assert state.water_ledger == {} and state.last_cycle_liters is None
    assert zone.number("zone_flow_l_min") == 0.0 and not zone.has_water_volume
    # A tip after the upgrade adds one tip of rain, not a jump.
    before = state.rain_tracker().latest_cumulative()
    hass.states.async_set(RAIN_COUNTER, "450")
    await hass.async_block_till_done()
    assert state.rain_tracker().latest_cumulative() - before == pytest.approx(zone.number("rain_mm_per_tip"), abs=0.01)
