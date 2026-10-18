"""Upgrading from 1.7.3: a zone saved before the 1.7.4 fields (soil-wet choice,
self-tuning switch, run lengths for the due buffer, ignored warnings) keeps its
history and flags, every new setting starts at the value that used to be fixed,
and nothing is re-fired."""
from dataclasses import asdict

import pytest

from custom_components.zoneflow import visibility
from custom_components.zoneflow.const import DOMAIN, STORAGE_VERSION
from custom_components.zoneflow.state_store import IrrigationState

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

NEW_IN_1_7_4 = (
    "soil_wet_action", "self_tune_enabled", "check_ignored", "last_routine_run_seconds",
    "last_routine_run_for_ts", "last_deep_run_seconds", "last_deep_run_for_ts",
)


@pytest.mark.asyncio
async def test_a_1_7_3_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"))
    old = asdict(IrrigationState())
    for name in NEW_IN_1_7_4:  # a 1.7.3 file does not have these keys at all
        old.pop(name)
    now = 1_790_000_000.0
    old.update(
        last_routine_ts=now - 86400,
        last_deep_soak_ts=now - 3 * 86400,
        rain_day_history_mm=[0.0] * 10,
        rain_threshold_flags={"24h": True, "4d": True, "7d": False},
        last_significant_rain_ts=now - 40000,
        auto_hidden=[["number", "rain_eff_low"], ["number", "rain_eff_mid"], ["number", "rain_eff_high"]],
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

    # the new saved fields start at the old behaviour
    defaults = IrrigationState()
    for name in NEW_IN_1_7_4:
        assert getattr(state, name) == getattr(defaults, name), name
    assert state.soil_wet_action == "finish" and state.self_tune_enabled is True
    assert state.check_ignored == [] and state.last_routine_run_seconds == 0.0

    # the new settings start at the values that used to be fixed
    assert zone.number("routine_min_pulse_minutes") == 1.0 and zone.number("deep_soak_min_pulse_minutes") == 5.0
    assert zone.number("self_tune_streak") == 3.0 and zone.number("self_tune_step_days") == 0.5
    assert zone.number("valve_timer_minutes") == 0.0
    assert zone.summary_time.hour == 18 and zone.fertilize_time.hour == 9
    # the due buffer is the old 6 hours until a run length is stored
    assert zone._routine_buffer() == 6 * 3600 and zone._deep_buffer() == 6 * 3600
    # a rain check with no rain changes nothing
    zone._check_significant_rain()
    assert state.last_significant_rain_ts == now - 40000

    # the three Rain Efficiency sliders the old version hid are shown now
    registry = __import__("homeassistant.helpers.entity_registry", fromlist=["x"]).async_get(hass)
    for key in ("rain_eff_low", "rain_eff_mid", "rain_eff_high"):
        reg = next(e for e in registry.entities.values() if e.platform == DOMAIN and e.translation_key == key)
        assert reg.hidden_by is None, key
    assert ("number", "rain_eff_low") not in visibility.hidden_for(zone)

