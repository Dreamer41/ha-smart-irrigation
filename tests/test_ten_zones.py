"""Ten zones at once, the way a bigger garden runs: two shared pumps (five
zones each), all due at the same scheduled moment, with a mix of what 1.5.0
added -- one paused, one in frost, one with a weekly summary. Every zone
waters exactly once (or says why not), no two valves on one pump are ever
open together, and each Status sentence matches what happened."""
import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback

from custom_components.zoneflow import summary
from custom_components.zoneflow.const import DOMAIN

from .scenario_harness import CompressedTime
from .test_scenarios_cycles import _history
from .test_smoke_setup import OUTDOOR_TEMP, RAIN_COUNTER, make_entry

VALVES = [f"switch.valve_{i}" for i in range(10)]
COLD = "sensor.cold_corner"


@pytest.mark.asyncio
async def test_ten_zones_on_two_shared_pumps(hass, fake_valve_services, monkeypatch, tmp_path):
    sent = []

    async def _notify(call):
        sent.append(call.data)

    hass.services.async_register("notify", "send_message", _notify)
    for valve in VALVES:
        hass.states.async_set(valve, "off")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    hass.states.async_set(COLD, "-1.0")
    hass.states.async_set("notify.phone", "unknown")
    await hass.async_block_till_done()
    entries = [
        make_entry(
            hass,
            zone_name=f"Zone {i}",
            valve_entity=VALVES[i],
            pump_power_entity=None,
            pump_id="Pump A" if i < 5 else "Pump B",
            outdoor_temp_entity=COLD if i == 7 else OUTDOOR_TEMP,
            notify_entity="notify.phone",
            csv_path=str(tmp_path / f"z{i}.csv"),
        )
        for i in range(10)
    ]
    assert await hass.config_entries.async_setup(entries[0].entry_id)
    await hass.async_block_till_done()
    assert all(e.state == ConfigEntryState.LOADED for e in entries)
    zones = [hass.data[DOMAIN][e.entry_id] for e in entries]
    clock = CompressedTime(hass, VALVES).install(monkeypatch)
    for zone in zones:
        _history(zone, last_routine_days_ago=4, last_deep_days_ago=1, peaks=(30.5, 30.5, 30.5))
        zone.store.state.summary_day = "mon"
    await zones[3].set_paused(True)

    # Record every valve change to check the pumps.
    open_now: set[str] = set()
    overlaps = []

    @callback
    def _changed(event):
        entity = event.data.get("entity_id")
        if entity not in VALVES:
            return
        if event.data["new_state"].state == "on":
            group = VALVES[:5] if VALVES.index(entity) < 5 else VALVES[5:]
            if open_now & set(group):
                overlaps.append((entity, set(open_now)))
            open_now.add(entity)
        else:
            open_now.discard(entity)

    unsub = hass.bus.async_listen("state_changed", _changed)
    try:
        await asyncio.gather(*(zone.run_routine_irrigation() for zone in zones))
        await hass.async_block_till_done()
    finally:
        unsub()

    assert overlaps == []
    for i, zone in enumerate(zones):
        code = zone.status()["code"]
        pulses = clock.pulses_for(VALVES[i])
        if i == 3:
            assert code == "paused" and pulses == []
        elif i == 7:
            assert code == "waiting_frost" and pulses == []
        else:
            assert code == "done", (i, code)
            assert pulses and zone.store.state.summary_runs == 1
            assert not zone.store.state.lock_on

    # One weekly summary for the one phone, all ten zones in it.
    sent.clear()
    assert await summary.async_send(hass, day="mon") == 1
    lines = sent[0]["message"].split("\n")
    assert len(lines) == 10
    assert lines[3].startswith("Zone 3: no watering") and lines[3].endswith(" · paused")
