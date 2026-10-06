"""Water use (1.6.5): Zone Flow, the daily ledger, the Water Used sensors and
the litres under the last watering."""
import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from custom_components.zoneflow import units
from custom_components.zoneflow.const import DOMAIN

from .test_presets_and_flow_rate import _options, _zone
from .test_scenarios_cycles import _history, _set, _zone as _cycle_zone


async def _watered(hass, controller):
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_without_zone_flow_a_watering_counts_mm_only(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, _ = await _cycle_zone(hass, monkeypatch, tmp_path)
    await _watered(hass, controller)
    used = controller.water_used()
    assert used["mm_30d"] == pytest.approx(20.0, abs=0.3) and used["liters_30d"] == 0.0
    assert controller.store.state.last_cycle_liters is None
    assert not controller.has_water_volume


@pytest.mark.asyncio
async def test_zone_flow_turns_valve_minutes_into_litres(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, _ = await _cycle_zone(hass, monkeypatch, tmp_path)
    await controller.numbers["zone_flow_l_min"].async_set_metric_value(2.0)
    await _watered(hass, controller)
    minutes = controller.store.state.last_cycle_runtime_min
    assert controller.store.state.last_cycle_liters == pytest.approx(minutes * 2.0, abs=0.1)
    used = controller.water_used()
    assert used["liters_30d"] == pytest.approx(minutes * 2.0, abs=0.1)
    assert used["liters_year"] == pytest.approx(used["liters_30d"])
    assert controller.has_water_volume


@pytest.mark.asyncio
async def test_the_30_day_total_rolls_and_the_year_total_is_the_calendar_year(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, _ = await _cycle_zone(hass, monkeypatch, tmp_path)
    today = dt_util.now().date()
    ledger = controller.store.state.water_ledger
    ledger[today.isoformat()] = {"mm": 10.0, "l": 100.0}
    ledger[(today.replace(month=1, day=1)).isoformat()] = {"mm": 5.0, "l": 50.0}  # this year
    ledger[(today.replace(month=1, day=1).replace(year=today.year - 1)).isoformat()] = {"mm": 99.0, "l": 990.0}  # last year
    used = controller.water_used()
    assert used["liters_year"] == pytest.approx(150.0)
    assert used["liters_30d"] in (100.0, 150.0)  # 1 Jan counts only while it is within 30 days
    # Old days are dropped as new ones are added.
    ledger[(today.replace(year=today.year - 2)).isoformat()] = {"mm": 1.0, "l": 1.0}
    controller._add_to_water_ledger(1.0, None)
    assert (today.replace(year=today.year - 2)).isoformat() not in controller.store.state.water_ledger


@pytest.mark.asyncio
async def test_the_water_sensors_follow_the_zone_units(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, _ = await _cycle_zone(hass, monkeypatch, tmp_path)
    await controller.numbers["zone_flow_l_min"].async_set_metric_value(3.785411784)
    await _watered(hass, controller)
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{controller.entry.entry_id}_water_used_year")
    assert entity_id is not None
    last = registry.async_get_entity_id("sensor", DOMAIN, f"{controller.entry.entry_id}_last_water_delivered")
    # The sensors poll; ask for a refresh.
    from homeassistant.helpers.entity_component import async_update_entity

    await async_update_entity(hass, entity_id)
    await async_update_entity(hass, last)
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(controller.water_used()["liters_year"], abs=0.1)
    assert state.attributes["unit_of_measurement"] == "L"
    assert state.attributes["depth_unit"] == "mm"
    attrs = hass.states.get(last).attributes
    assert attrs["volume"] == pytest.approx(controller.store.state.last_cycle_liters, abs=0.1)


def test_zone_flow_converts_to_gallons():
    assert units.to_display("zone_flow_l_min", 3.785411784, True) == pytest.approx(1.0)
    assert units.to_metric("zone_flow_l_min", 1.0, True) == pytest.approx(3.785411784)
    assert units.unit("zone_flow_l_min", "L/min", True) == "gal/min"


@pytest.mark.asyncio
async def test_zone_flow_from_the_heads(hass, fake_valve_services, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    result = await _options(hass, entry, "zone_flow")
    assert result["step_id"] == "zone_flow"
    # 50 drippers x 2 L/h = 100 L/h = 1.67 L/min
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"heads": 50, "head_flow": 2.0, "head_flow_unit": "L/h"}
    )
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "zone_flow_set"
    assert controller.number("zone_flow_l_min") == pytest.approx(1.67, abs=0.01)
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.24)  # calibration untouched

    result = await _options(hass, entry, "zone_flow")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"heads": 8, "head_flow": 5.0, "head_flow_unit": "L/min"}
    )
    assert controller.number("zone_flow_l_min") == pytest.approx(40.0)

    result = await _options(hass, entry, "zone_flow")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"heads": 5000, "head_flow": 9000.0, "head_flow_unit": "L/min"}
    )
    assert result["reason"] == "zone_flow_out_of_range"
    assert controller.number("zone_flow_l_min") == pytest.approx(40.0)


@pytest.mark.asyncio
async def test_the_flow_rate_steps_also_set_zone_flow(hass, fake_valve_services, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    result = await _options(hass, entry, "flow_rate")
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"emitters": 60, "emitter_flow": 2.0, "area": 10.0}
    )
    assert controller.number("zone_flow_l_min") == pytest.approx(2.0)  # 120 L/h

    result = await _options(hass, entry, "flow_volume")
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"minutes": 15, "volume": 36.0, "area": 10.0}
    )
    assert controller.number("zone_flow_l_min") == pytest.approx(2.4)


@pytest.mark.asyncio
async def test_a_flow_meter_that_counts_nothing_falls_back_to_zone_flow(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, _ = await _cycle_zone(hass, monkeypatch, tmp_path)
    await controller.numbers["zone_flow_l_min"].async_set_metric_value(2.0)
    controller._run_liters = 0.0  # the meter read both ends and saw no water
    controller._count_for_summary(10.0, "routine")
    assert controller.store.state.last_cycle_liters == pytest.approx(20.0)
    controller._run_liters = 15.0  # a meter that counted is believed
    controller._count_for_summary(10.0, "routine")
    assert controller.store.state.last_cycle_liters == pytest.approx(15.0)


@pytest.mark.asyncio
async def test_a_refused_emitter_entry_leaves_zone_flow_alone(hass, fake_valve_services, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    await controller.numbers["zone_flow_l_min"].async_set_metric_value(3.0)
    result = await _options(hass, entry, "flow_rate")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"emitters": 100, "emitter_flow": 10.0, "area": 0.1}
    )
    assert result["reason"] == "flow_rate_out_of_range"
    assert controller.number("zone_flow_l_min") == pytest.approx(3.0)
