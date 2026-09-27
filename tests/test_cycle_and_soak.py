"""Cycle and soak from the soil: each watering is split into as many pulses
as the soil needs to take it in without runoff (plus one on a moderate
slope, two on a steep one), never fewer than the zone's pulse-count
setting; the soak between pulses follows the soil when it is picked.
Existing zones keep their settings -- they only gain pulses where the soil
or slope needs them."""
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import (
    CONF_DRAINAGE,
    CONF_INITIAL_NUMBERS,
    CONF_IRRIGATION_METHOD,
    CONF_SLOPE,
    CONF_SOIL_TYPE,
    CONF_ZONE_NAME,
    DOMAIN,
)

from .test_config_flow import _minimal_entities_input, _through_climate
from .test_scenarios_cycles import _history, _set, _zone
from .test_smoke_setup import VALVE


def test_the_soil_table():
    # Texas A&M's cycle-and-soak runtimes, as depth per pulse.
    assert calc.mm_per_pulse("clay", "medium") == 3.0
    assert calc.mm_per_pulse("loam", "fast") == 15.0
    assert calc.mm_per_pulse("sandy", "unknown") == 30.0
    assert calc.mm_per_pulse("loam", "slow") == pytest.approx(10.5)  # compact subsoil: 70 %
    # 14 mm routine, 25 mm deep soak
    assert calc.soil_pulse_count(14, "clay", "medium", "flat", 1) == 5
    assert calc.soil_pulse_count(25, "clay", "medium", "flat", 1) == 8  # capped
    assert calc.soil_pulse_count(14, "loam", "medium", "flat", 1) == 1
    assert calc.soil_pulse_count(14, "loam", "medium", "slight", 1) == 1
    assert calc.soil_pulse_count(14, "loam", "medium", "moderate", 1) == 2
    assert calc.soil_pulse_count(14, "loam", "medium", "steep", 1) == 3
    assert calc.soil_pulse_count(14, "loam", "medium", "flat", 3) == 3  # the setting is the minimum
    assert calc.soil_pulse_count(15, "loam", "medium", "flat", 1) == 1  # exactly one pulse's worth
    assert calc.soak_minutes("sandy", "medium") == 30.0
    assert calc.soak_minutes("clay_loam", "medium") == 60.0
    assert calc.soak_minutes("loam", "slow") == 60.0
    assert calc.starting_pulse_count("sandy", "drip") == 2
    assert calc.starting_pulse_count("sandy", "sprinkler") == 1
    assert calc.starting_pulse_count("clay", "drip") == 1


async def _run_routine(hass, controller):
    # Hot tier, 4 days since the last run: 20 mm to put on.
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("soil", "drainage", "slope", "pulses"),
    [
        ("loam", "medium", "flat", 3),  # needs 2: the zone's setting (3) stays
        ("clay", "medium", "flat", 7),  # 20 mm / 3 mm
        ("loam", "medium", "steep", 4),  # 2 + 2 for the slope
        ("clay_loam", "slow", "moderate", 6),  # 20 / 4.9 -> 5, + 1
    ],
)
async def test_an_existing_zone_gets_the_pulses_its_soil_needs(
    hass, fake_valve_services, monkeypatch, tmp_path, soil, drainage, slope, pulses
):
    # Set up like a zone from before this existed: pulse count 3, 20-min soaks.
    controller, clock, _ = await _zone(
        hass, monkeypatch, tmp_path, soil_type=soil, drainage=drainage, slope=slope
    )
    assert controller.number("routine_pulse_count") == 3 and controller.number("routine_pulse_rest_minutes") == 20
    await _run_routine(hass, controller)
    runs = clock.pulses_for(VALVE)
    assert len(runs) == pulses and len(set(runs)) == 1
    assert sum(runs) * controller.number("flow_rate_mm_per_min") == pytest.approx(20.0, abs=0.3)
    # Its own soak setting, untouched.
    assert [s for s in clock.sleeps_seconds if s > 0] == [1200] * (pulses - 1)


@pytest.mark.asyncio
async def test_a_deep_soak_on_clay_is_capped_at_eight_pulses(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path, soil_type="clay")
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=20)
    await _set(controller, deep_soak_max_runtime_minutes=300)
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 8


@pytest.mark.asyncio
async def test_the_dropdowns_change_the_pulses_and_the_soak(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path, soil_type="loam")

    async def pick(what, option):
        entity_id = next(e for e in hass.states.async_entity_ids("select") if e.endswith(what))
        await hass.services.async_call("select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True)

    await pick("_slope", "steep")
    assert controller.slope == "steep"
    assert controller.number("routine_pulse_rest_minutes") == 20  # slope leaves the soak alone
    await pick("_soil_type", "clay")
    assert controller.number("routine_pulse_rest_minutes") == 60
    assert controller.number("deep_soak_pulse_rest_minutes") == 60
    await pick("_soil_type", "sandy")
    assert controller.number("routine_pulse_rest_minutes") == 30
    await pick("_drainage", "slow")
    assert controller.number("routine_pulse_rest_minutes") == 60

    await _run_routine(hass, controller)
    # Sand, slow drainage: 20 mm / 21 mm -> 1, + 2 for the steep slope; the setting (3) is the minimum.
    assert len(clock.pulses_for(VALVE)) == 3
    assert [s for s in clock.sleeps_seconds if s > 0] == [3600] * 2


@pytest.mark.asyncio
async def test_configure_takes_over_from_the_dropdowns(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, _ = await _zone(hass, monkeypatch, tmp_path, soil_type="loam")
    entry = controller.entry
    controller.store.state.slope_override = "steep"  # picked on the device page
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "settings"})
    defaults = {k.schema: k.default() for k in result["data_schema"].schema if callable(getattr(k, "default", None))}
    assert defaults[CONF_SLOPE] == "steep"  # the form shows what the zone uses
    answer = {k: v for k, v in defaults.items() if v is not None}
    answer[CONF_SOIL_TYPE] = "clay"
    answer[CONF_SLOPE] = "flat"
    result = await hass.config_entries.options.async_configure(result["flow_id"], answer)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert (controller.soil_type, controller.slope) == ("clay", "flat")
    assert controller.number("routine_pulse_rest_minutes") == 60  # the soil changed: the soak follows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("soil", "method", "count", "soak"),
    [("sandy", "drip", 2.0, 30.0), ("clay", "drip", 1.0, 60.0), ("loam", "sprinkler", 1.0, 30.0)],
)
async def test_a_new_zone_starts_from_its_soil(hass, soil, method, count, soak):
    hass.states.async_set("switch.valve", "off")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONE_NAME: "Bed"})
    entities = _minimal_entities_input()
    entities.update({CONF_SOIL_TYPE: soil, CONF_DRAINAGE: "medium", CONF_IRRIGATION_METHOD: method})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entities)
    result = await _through_climate(hass, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    assert numbers["routine_pulse_count"] == numbers["deep_soak_pulse_count"] == count
    assert numbers["routine_pulse_rest_minutes"] == numbers["deep_soak_pulse_rest_minutes"] == soak
