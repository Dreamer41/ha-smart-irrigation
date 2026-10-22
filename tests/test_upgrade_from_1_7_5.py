"""Upgrading from 1.7.5: 1.7.6 stores no new state, so a saved zone keeps all its history and flags, and the
one new setting (Rain Ignored Below) starts at the 3 mm that used to be fixed: the rain credit comes out
exactly as it did."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow import visibility
from custom_components.zoneflow.const import DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


@pytest.mark.asyncio
async def test_a_1_7_5_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = asdict(IrrigationState())  # 1.7.6 added no saved field: a 1.7.5 file has the same keys
    now = 1_790_000_000.0
    old.update(
        last_routine_ts=now - 86400,
        last_deep_soak_ts=now - 3 * 86400,
        rain_day_history_mm=[0.0, 4.0, 12.0, 0.0, 6.0, 0.0, 0.0, 0.0, 0.0, 0.0],
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
    assert state.rain_day_history_mm[:5] == [0.0, 4.0, 12.0, 0.0, 6.0]
    assert state.rain_threshold_flags == {"24h": True, "4d": True, "7d": False}
    assert state.last_significant_rain_ts == now - 40000

    # the new setting starts at the value that used to be fixed, and is shown (not hidden by an old rule)
    assert zone.number("rain_ignore_below_mm") == 3.0
    registry = __import__("homeassistant.helpers.entity_registry", fromlist=["x"]).async_get(hass)
    reg = next(e for e in registry.entities.values() if e.platform == DOMAIN and e.translation_key == "rain_ignore_below_mm")
    assert reg.hidden_by is None
    assert ("number", "rain_ignore_below_mm") not in visibility.hidden_for(zone)

    # with that value the rain credit is what 1.7.5 gave, band by band
    low, mid, high = zone.number("rain_eff_low"), zone.number("rain_eff_mid"), zone.number("rain_eff_high")
    for mm in (0.0, 2.9, 3.0, 3.5, 4.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0):
        old_credit = (
            0.0 if mm <= 3 else (mm - 3) / 2 * low if mm <= 5 else low + (mm - 5) / 5 * (mid - low) if mm <= 10
            else mid + (mm - 10) / 10 * (high - mid) if mm <= 20 else high
        )
        assert calc.rain_efficiency(mm, low, mid, high, zone.number("rain_ignore_below_mm")) == pytest.approx(old_credit), mm
