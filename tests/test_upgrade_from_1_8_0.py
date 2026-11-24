"""Upgrading from 1.8.0/1.8.1 to 1.8.2 (OpenSprinkler stations): nothing new is saved, so a
saved zone loads exactly as it was. A zone that already named an OpenSprinkler station switch as its
valve, and was left mid-run by a restart, has the station stopped (read from its Station Running sensor)."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow.const import CONF_VALVE_ENTITY, DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_opensprinkler import RUNNING, SWITCH, fake_opensprinkler  # noqa: F401 - the fixture
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, make_entry


async def _boot(hass, hass_storage, tmp_path, valve, **saved):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"), **{CONF_VALVE_ENTITY: valve})
    old = asdict(IrrigationState())  # the 1.8.0 file has every field 1.8.2 knows
    old.update(saved)
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((PUMP, "999"), (RAIN_COUNTER, "10"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_a_zone_on_a_plain_switch_loads_unchanged(hass, fake_valve_services, hass_storage, tmp_path):
    from .test_smoke_setup import VALVE

    hass.states.async_set(VALVE, "off")
    zone = await _boot(hass, hass_storage, tmp_path, VALVE, demand_model="et_curve")
    assert zone.store.state.demand_model == "et_curve"
    assert zone.status()["text"]


@pytest.mark.asyncio
async def test_a_station_zone_left_running_by_a_restart_is_stopped(hass, fake_opensprinkler, hass_storage, tmp_path):  # noqa: F811
    hass.states.async_set(RUNNING, "on")
    zone = await _boot(
        hass, hass_storage, tmp_path, SWITCH,
        lock_on=True, lock_valve=SWITCH, lock_set_ts=1.0,
    )
    assert ("stop", {"entity_id": SWITCH}) in fake_opensprinkler
    assert hass.states.get(RUNNING).state == "off"
    assert zone.store.state.lock_on is False
