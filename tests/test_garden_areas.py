"""Garden areas (1.6.6): a name of the person's own on each zone, for
grouping the zones in the cards. A crop is in its greenhouse's area."""
import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.zoneflow.const import CONF_GARDEN_AREA, DOMAIN

from .test_presets_and_flow_rate import _options, _zone


async def _set_area(hass, entry, name):
    result = await _options(hass, entry, "garden_area")
    assert result["step_id"] == "garden_area"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_GARDEN_AREA: name})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_a_zone_has_no_area_until_one_is_set(hass, fake_valve_services, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    assert controller.garden_area is None


@pytest.mark.asyncio
async def test_setting_an_area_names_it_and_blank_clears_it(hass, fake_valve_services, tmp_path):
    entry, _ = await _zone(hass, tmp_path)
    await _set_area(hass, entry, "  Back   yard ")
    assert hass.data[DOMAIN][entry.entry_id].garden_area == "Back yard"
    await _set_area(hass, entry, "")
    assert hass.data[DOMAIN][entry.entry_id].garden_area is None
    assert CONF_GARDEN_AREA not in entry.options  # kept with the zone, not in its setup


@pytest.mark.asyncio
async def test_the_same_name_in_other_letters_is_the_same_area(hass, fake_valve_services, tmp_path):
    entry, _ = await _zone(hass, tmp_path)
    await _set_area(hass, entry, "Backyard")
    from .test_smoke_setup import make_entry

    other = make_entry(hass, csv_path=str(tmp_path / "g.csv"), zone_name="Other Zone", valve_entity="switch.other_valve")
    hass.states.async_set("switch.other_valve", "off")
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    await _set_area(hass, other, "backyard")
    assert hass.data[DOMAIN][other.entry_id].garden_area == "Backyard"


@pytest.mark.asyncio
async def test_the_status_sensor_tells_the_cards_the_area(hass, fake_valve_services, tmp_path):
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_component import async_update_entity

    entry, _ = await _zone(hass, tmp_path)
    await _set_area(hass, entry, "Front yard")
    registry = er.async_get(hass)
    status = next(
        e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.translation_key == "status"
    )
    await async_update_entity(hass, status)
    assert hass.states.get(status).attributes["garden_area"] == "Front yard"


@pytest.mark.asyncio
async def test_the_zones_garden_area_field_sets_it_without_a_reload(hass, fake_valve_services, tmp_path):
    from homeassistant.helpers import entity_registry as er

    entry, controller = await _zone(hass, tmp_path)
    registry = er.async_get(hass)
    field = next(
        e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "text" and e.translation_key == "garden_area"
    )
    assert hass.states.get(field).state == ""
    await hass.services.async_call("text", "set_value", {"entity_id": field, "value": "  Front   yard"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id] is controller  # not reloaded
    assert controller.garden_area == "Front yard" and hass.states.get(field).state == "Front yard"
    # Saved with the zone's state, so it survives a reload.
    assert controller.store.state.garden_area == "Front yard"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].garden_area == "Front yard"
    await hass.services.async_call("text", "set_value", {"entity_id": field, "value": ""}, blocking=True)
    assert hass.data[DOMAIN][entry.entry_id].garden_area is None
