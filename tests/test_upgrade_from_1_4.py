"""Upgrading from 1.4.x: a zone's saved state from before 1.5.0 (no
decisions, pause, summary or offline records -- and perhaps keys a later
version wrote) loads, keeps its history and settings, and every new
feature starts from a sensible default."""
from dataclasses import asdict

import pytest

from homeassistant.helpers import entity_registry as er

from custom_components.zoneflow.const import DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

NEW_IN_1_5 = {
    "auto_hidden", "notify_level", "decisions", "paused", "paused_since_ts", "pause_ended_ts", "pause_until_ts",
    "summary_day", "summary_since_ts", "summary_runs", "summary_minutes", "summary_mm", "summary_liters",
    "summary_skip_days", "offline_since",
}


@pytest.mark.asyncio
async def test_a_1_4_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = {k: v for k, v in asdict(IrrigationState()).items() if k not in NEW_IN_1_5}
    old.update(last_routine_ts=1_790_000_000.0, planting_date_ts=1_780_000_000.0, some_future_key=True)
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "0"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    state = zone.store.state
    assert state.last_routine_ts == 1_790_000_000.0 and state.planting_date_ts == 1_780_000_000.0
    assert state.notify_level == "all" and state.paused is False and state.decisions == {}
    assert state.summary_day == "off" and state.offline_since == {}
    status = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_status") and "soil" not in s.entity_id and "deficit" not in s.entity_id)
    assert status.state and status.attributes["code"] in ("next", "next_deep_soak")
    # Everyday entities stay visible; nothing the zone uses got hidden.
    assert not any(
        e.hidden_by for e in er.async_get(hass).entities.values()
        if e.config_entry_id == entry.entry_id and e.translation_key in ("status", "pause", "run_routine")
    )
