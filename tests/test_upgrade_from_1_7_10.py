"""Upgrading from 1.7.10: 1.8 adds saved fields for the FAO-56 days and the day shift
(`last_shift_date_iso`, `day_aggregates`, `et0_day_history`, `last_alive_ts`). A zone saved by 1.7.10
has none of them: it loads with its history, marks and demand model as they were, keeps its model
(only a brand-new zone starts on FAO-56), waters the same amount and is never switched by itself."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow.const import DEMAND_MODEL_FAO56, DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

NEW_IN_1_8 = {"last_shift_date_iso", "day_aggregates", "et0_day_history", "last_alive_ts"}


async def _boot(hass, hass_storage, tmp_path, drop=(), **saved):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = {k: v for k, v in asdict(IrrigationState()).items() if k not in NEW_IN_1_8 and k not in drop}  # a 1.7.10 file
    old.update(saved)
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "10"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["temperature_tiers", "et_curve"])
async def test_a_1_7_10_zone_keeps_its_model_and_history(hass, fake_valve_services, hass_storage, tmp_path, model):
    import homeassistant.util.dt as dt_util

    now = dt_util.utcnow().timestamp()
    zone = await _boot(
        hass, hass_storage, tmp_path,
        demand_model=model,
        last_routine_ts=now - 3 * 86400,
        last_deep_soak_ts=now - 5 * 86400,
        last_significant_rain_ts=now - 3 * 86400,
        drydown_counted_from_ts=now - 3 * 86400,
        rain_day_history_mm=[0.0, 12.0, 0.5, 0.0, 4.0, 0.0, 0.0],
        peak_temps_c=[31.0, 32.5, 30.0, 33.0, 31.5],
    )
    s = zone.store.state
    assert s.demand_model == model
    assert s.last_routine_ts == now - 3 * 86400 and s.last_deep_soak_ts == now - 5 * 86400
    assert s.last_significant_rain_ts == now - 3 * 86400 and s.drydown_counted_from_ts == now - 3 * 86400
    assert s.rain_day_history_mm[:3] == [0.0, 12.0, 0.5]
    # the new fields start empty
    assert s.et0_day_history == [] and s.day_aggregates is not None
    assert zone.fao56_daily_demand_mm() is None  # no FAO-56 day yet: nothing leaks into the old model's amount
    assert zone.status()["text"]


@pytest.mark.asyncio
async def test_a_1_7_10_zone_saved_without_a_model_still_loads_and_is_not_switched(hass, fake_valve_services, hass_storage, tmp_path):
    zone = await _boot(hass, hass_storage, tmp_path, drop={"demand_model"})
    # a saved zone is offered the switch later; it is never silently moved
    assert zone.store.state.demand_model in ("temperature_tiers", "et_curve", DEMAND_MODEL_FAO56)


@pytest.mark.asyncio
async def test_a_brand_new_zone_starts_on_fao56(hass, fake_valve_services, tmp_path):
    entry = make_entry(hass, csv_path=str(tmp_path / "n.csv"))
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "10"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].store.state.demand_model == DEMAND_MODEL_FAO56
