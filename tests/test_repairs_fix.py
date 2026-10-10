"""Fix buttons on ZoneFlow's repairs (1.7.0)."""
from __future__ import annotations

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir

from custom_components.zoneflow import issues, repairs
from custom_components.zoneflow.const import CONF_NOTIFY_ENTITY, CONF_AREA_ID, DOMAIN

from .test_areas import AREA_TEMP, _area
from .test_plants import _boot, _ctl, _zone
from .test_smoke_setup import OUTDOOR_TEMP, VALVE


async def _flow(hass, issue_id):
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.is_fixable
    flow = await repairs.async_create_fix_flow(hass, issue_id, issue.data)
    flow.hass = hass
    flow.issue_id = issue_id
    flow.handler = DOMAIN
    flow.flow_id = "test"
    return flow


@pytest.mark.asyncio
async def test_the_three_repairs_are_fixable_and_carry_what_to_fix(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE, **{CONF_NOTIFY_ENTITY: "notify.gone"})
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    c.store.state.offline_since[OUTDOOR_TEMP] = 0.0  # offline for ages
    c.store.state.offline_since["notify.gone"] = 0.0
    issues.async_check(c)
    registry = ir.async_get(hass)
    sensor = registry.async_get_issue(DOMAIN, f"{zone.entry_id}_sensor_offline_temperature")
    assert sensor.is_fixable and sensor.data == {"entry_id": zone.entry_id, "kind": "sensor", "role": "temperature", "entity": OUTDOOR_TEMP}
    assert registry.async_get_issue(DOMAIN, f"{zone.entry_id}_notify_missing").data["kind"] == "notify"
    assert registry.async_get_issue(DOMAIN, f"{zone.entry_id}_flow_rate_default").data["kind"] == "flow_rate"
    # A valve that is down has no fix button: there is nothing to pick.
    hass.states.async_set(VALVE, "unavailable")
    c.store.state.offline_since[VALVE] = 0.0
    issues.async_check(c)
    assert not registry.async_get_issue(DOMAIN, f"{zone.entry_id}_valve_unavailable").is_fixable


@pytest.mark.asyncio
async def test_fixing_the_phone_and_clearing_it(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE, **{CONF_NOTIFY_ENTITY: "notify.gone"})
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    c.store.state.offline_since["notify.gone"] = 0.0
    issues.async_check(c)
    flow = await _flow(hass, f"{zone.entry_id}_notify_missing")
    form = await flow.async_step_init()
    assert form["type"] is FlowResultType.FORM and form["description_placeholders"]["entity"] == "notify.gone"
    hass.states.async_set("notify.mobile_app_pixel", "unknown")
    done = await flow.async_step_init({CONF_NOTIFY_ENTITY: "notify.mobile_app_pixel"})
    assert done["type"] is FlowResultType.CREATE_ENTRY and zone.options[CONF_NOTIFY_ENTITY] == "notify.mobile_app_pixel"
    done = await (await _flow_again(hass, zone)).async_step_init({})
    assert zone.options[CONF_NOTIFY_ENTITY] is None  # left empty: no phone


async def _flow_again(hass, zone):
    hass.config_entries.async_update_entry(zone, options={**zone.options, CONF_NOTIFY_ENTITY: "notify.gone"})
    await hass.async_block_till_done()
    c = _ctl(hass, zone)
    c.store.state.offline_since["notify.gone"] = 0.0
    issues.async_check(c)
    return await _flow(hass, f"{zone.entry_id}_notify_missing")


@pytest.mark.asyncio
async def test_replacing_a_sensor_that_is_the_zones_own_or_its_areas(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE)  # its own thermometer from make_entry
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    c.store.state.offline_since[OUTDOOR_TEMP] = 0.0
    issues.async_check(c)
    flow = await _flow(hass, f"{zone.entry_id}_sensor_offline_temperature")
    hass.states.async_set("sensor.new_temp", "21", {"device_class": "temperature"})
    done = await flow.async_step_init({"replacement": "sensor.new_temp"})
    assert done["type"] is FlowResultType.CREATE_ENTRY and zone.options["outdoor_temp_entity"] == "sensor.new_temp"

    # A zone that takes the thermometer from its area: the area's setting is fixed.
    area = _area(hass)
    other = _zone(hass, "Chilis", "switch.valve_peppers", **{CONF_AREA_ID: area.entry_id, "outdoor_temp_entity": None, "rain_counter_entity": None})
    hass.states.async_set("switch.valve_peppers", "off")
    hass.states.async_set(AREA_TEMP, "28")
    assert await hass.config_entries.async_setup(area.entry_id)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    oc = _ctl(hass, other)
    assert oc.outdoor_temp_entity == AREA_TEMP
    hass.states.async_set(AREA_TEMP, "unavailable")
    oc.store.state.offline_since[AREA_TEMP] = 0.0
    issues.async_check(oc)
    flow = await _flow(hass, f"{other.entry_id}_sensor_offline_temperature")
    await flow.async_step_init({})  # take it away
    assert area.options["outdoor_temp_entity"] is None and "outdoor_temp_entity" not in other.options


@pytest.mark.asyncio
async def test_the_flow_rate_fix_runs_the_valve_then_takes_the_measurement(hass, fake_valve_services, monkeypatch, tmp_path):
    from .test_scenarios_cycles import _history, _zone as scenario_zone

    controller, clock, _ = await scenario_zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=3)
    controller.numbers["flow_rate_mm_per_min"].metric_value = 0.24  # the untouched example
    issues.async_check(controller)
    flow = await _flow(hass, f"{controller.entry.entry_id}_flow_rate_default")
    form = await flow.async_step_init()
    assert form["step_id"] == "init"
    nxt = await flow.async_step_init({"run": True})
    await hass.async_block_till_done()
    assert nxt["step_id"] == "measure" and clock.pulses_for(VALVE) == [15]
    bad = await flow.async_step_measure({"volume": 5000, "area": 1, "minutes": 1})
    assert bad["errors"] == {"base": "out_of_range"}
    done = await flow.async_step_measure({"volume": 30, "area": 10, "minutes": 15})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.2, abs=0.001)


@pytest.mark.asyncio
async def test_a_phone_the_zone_gets_from_its_area_is_fixed_on_the_area(hass, fake_valve_services):
    area = _area(hass, **{CONF_NOTIFY_ENTITY: "notify.gone"})
    zone = _zone(hass, "Chilis", "switch.valve_peppers", **{CONF_AREA_ID: area.entry_id, CONF_NOTIFY_ENTITY: None})
    hass.states.async_set("switch.valve_peppers", "off")
    await _boot(hass, area)
    c = _ctl(hass, zone)
    assert c.notify_entity == "notify.gone"
    c.store.state.offline_since["notify.gone"] = 0.0
    issues.async_check(c)
    flow = await _flow(hass, f"{zone.entry_id}_notify_missing")
    hass.states.async_set("notify.mobile_app_pixel", "unknown")
    await flow.async_step_init({CONF_NOTIFY_ENTITY: "notify.mobile_app_pixel"})
    assert area.options[CONF_NOTIFY_ENTITY] == "notify.mobile_app_pixel"
    assert not zone.options.get(CONF_NOTIFY_ENTITY)  # the zone keeps taking its area's phone


@pytest.mark.asyncio
async def test_a_greenhouse_thermometer_is_replaced_as_the_inside_sensor(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_INSIDE_TEMP_ENTITY

    from .test_zone_types import INSIDE_TEMP, _climate_only_entry

    house = _climate_only_entry(hass)
    await _boot(hass, house)
    c = _ctl(hass, house)
    hass.states.async_set(INSIDE_TEMP, "unavailable")
    c.store.state.offline_since[INSIDE_TEMP] = 0.0
    issues.async_check(c)
    flow = await _flow(hass, f"{house.entry_id}_sensor_offline_temperature")
    hass.states.async_set("sensor.gh_new", "27", {"device_class": "temperature"})
    await flow.async_step_init({"replacement": "sensor.gh_new"})
    assert house.options[CONF_INSIDE_TEMP_ENTITY] == "sensor.gh_new"
    assert not house.options.get("outdoor_temp_entity")  # not put where it does nothing

