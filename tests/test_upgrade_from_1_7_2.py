"""Upgrading from 1.7.2: a zone saved before the adjustable dry-down thresholds,
Watering time and Valve Overlap keeps its history and flags, the new settings
start at the old fixed values, and nothing is re-fired."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow.const import DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


@pytest.mark.asyncio
async def test_a_1_7_2_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = asdict(IrrigationState())  # 1.7.3 added no saved fields
    now = 1_790_000_000.0
    old.update(
        last_routine_ts=now - 86400,
        last_deep_soak_ts=now - 3 * 86400,
        rain_day_history_mm=[0.0] * 10,
        rain_threshold_flags={"24h": True, "4d": True, "7d": False},
        last_significant_rain_ts=now - 40000,
    )
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "10"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    state = zone.store.state
    # nothing of the saved history is reset
    assert state.last_routine_ts == now - 86400 and state.last_deep_soak_ts == now - 3 * 86400
    assert state.rain_threshold_flags == {"24h": True, "4d": True, "7d": False}
    assert state.last_significant_rain_ts == now - 40000
    # the new settings start at the values that used to be fixed / off
    assert (zone.number("drydown_rain_24h_mm"), zone.number("drydown_rain_4d_mm"), zone.number("drydown_rain_7d_mm")) == (35.0, 50.0, 100.0)
    assert zone.number("valve_overlap_seconds") == 0.0
    assert zone.schedule_summary()["routine_time"] == "05:30"
    # a rain check with no rain changes nothing
    zone._check_significant_rain()
    assert state.last_significant_rain_ts == now - 40000
