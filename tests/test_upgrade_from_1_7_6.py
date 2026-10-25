"""Upgrading from 1.7.6: 1.7.7 adds two saved fields for the rolling rain credit (`rain_window_base_ts`,
`rain_credit_marks`). A zone saved by 1.7.6 has neither: it loads with its history, flags, drying hold and
rain credit as they were, and a mark it carried keeps working the old way until it ends."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow.const import DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

NEW_IN_1_7_7 = {"rain_window_base_ts", "rain_credit_marks"}


async def _boot(hass, hass_storage, tmp_path, **saved):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = {k: v for k, v in asdict(IrrigationState()).items() if k not in NEW_IN_1_7_7}  # a 1.7.6 file
    old.update(saved)
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "10"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_a_1_7_6_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    import homeassistant.util.dt as dt_util

    now = dt_util.utcnow().timestamp()
    zone = await _boot(
        hass, hass_storage, tmp_path,
        last_routine_ts=now - 3600,
        last_deep_soak_ts=now - 3600,
        last_significant_rain_ts=now - 7200,
        rain_day_history_mm=[21.3, 21.6, 5.9, 6.0, 7.1, 0.9, 0.3, 0.6, 23.2, 19.2],
        rain_credit_spent_mm=12.57,
        rain_credit_spent_ts=now - 3600,
    )
    state = zone.store.state

    # the new fields start empty and nothing saved is reset
    assert state.rain_window_base_ts is None and state.rain_credit_marks == []
    assert state.last_routine_ts == now - 3600 and state.last_deep_soak_ts == now - 3600
    assert state.last_significant_rain_ts == now - 7200
    assert state.rain_day_history_mm[:3] == [21.3, 21.6, 5.9]
    assert state.rain_credit_spent_mm == 12.57 and state.rain_credit_spent_ts == now - 3600

    # the old mark is adopted into the rolling credit: the rain before it counts again, less its dose
    assert zone._chain_marks() == [(now - 3600, 12.57)]
    assert zone.rain_offset_mm() == pytest.approx(12.57, abs=0.01)
    assert zone._routine_plan().eff_rain_mm > 0.0

    # the drying hold is still on, and the status still says so
    status = zone.status()
    assert "Drying out after rain" in status["text"] or status["code"] == "waiting_drydown"


@pytest.mark.asyncio
async def test_the_first_mark_after_the_upgrade_starts_a_rolling_chain(hass, fake_valve_services, hass_storage, tmp_path):
    import homeassistant.util.dt as dt_util

    now = dt_util.utcnow().timestamp()
    zone = await _boot(
        hass, hass_storage, tmp_path,
        last_routine_ts=now - 6 * 86400,  # watered by the valve six days ago, no mark since
        rain_day_history_mm=[21.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    zone.today_rain_mm = lambda: 45.0
    real = zone.store.state.last_routine_ts
    await zone._on_rain_credit_check()

    state = zone.store.state
    assert state.rain_window_base_ts == real and len(state.rain_credit_marks) == 1
    assert state.last_routine_ts > real
    high = zone.number("rain_eff_high")
    dose = zone._routine_plan().interval_target_mm
    assert zone._routine_plan().eff_rain_mm == pytest.approx(45.0 * high + 21.0 * high - dose, abs=0.1)


@pytest.mark.asyncio
async def test_a_restart_keeps_a_rolling_chain_as_it_was(hass, fake_valve_services, hass_storage, tmp_path):
    """HA stopped and started again (also over midnight): a saved chain loads and counts the same."""
    import homeassistant.util.dt as dt_util

    now = dt_util.utcnow().timestamp()
    mark = now - 2 * 86400
    zone = await _boot(
        hass, hass_storage, tmp_path,
        last_routine_ts=mark,
        rain_window_base_ts=now - 6 * 86400,
        rain_credit_marks=[[mark, 10.0]],
        rain_credit_spent_mm=10.0,
        rain_credit_spent_ts=mark,
        rain_day_history_mm=[0.0, 30.0] + [0.0] * 8,
    )
    assert zone._chain_marks() == [(mark, 10.0)]
    assert 0.0 < zone.rain_offset_mm() <= 10.0
    assert zone.status()["text"]
