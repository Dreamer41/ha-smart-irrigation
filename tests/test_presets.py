"""Copy settings and saved presets (1.7.0)."""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.zoneflow import presets
from custom_components.zoneflow.const import (
    CONF_CLIMATE,
    CONF_PLANT,
    CONF_ROUTINE_TIME,
    CONF_START_FROM,
    CONF_START_STATE,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
)

from .test_config_flow import _minimal_entities_input
from .test_greenhouse_crops import VALVE_B
from .test_plants import _book, _boot, _ctl, _zone


async def _call(hass, service, **data):
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done()


def _device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)}).id


async def _tuned_source(hass):
    """A zone watered its own way, and a plain one to copy onto."""
    source, target = _zone(hass), _zone(hass, "Chilis", VALVE_B)
    await _boot(hass, source, target)
    c = _ctl(hass, source)
    for key, value in (
        ("target_weekly_mm", 31.0), ("crop_coefficient", 1.1), ("routine_pulse_count", 5.0),
        ("flow_rate_mm_per_min", 0.9), ("zone_flow_l_min", 55.0), ("rain_mm_per_tip", 0.5),
    ):
        await c.numbers[key].async_set_metric_value(value)
    c.store.state.demand_model = "et"
    c.store.state.mulch_status = "bare"
    c.store.state.planting_date_ts = 1_790_000_000.0
    c.store.state.health_notes = "greenfly"
    return source, target


@pytest.mark.asyncio
async def test_a_bundle_holds_watering_settings_and_nothing_of_the_hardware_or_the_plant(hass, fake_valve_services):
    source, _ = await _tuned_source(hass)
    bundle = presets.capture(_ctl(hass, source))
    assert bundle["numbers"]["target_weekly_mm"] == 31.0 and bundle["numbers"]["routine_pulse_count"] == 5.0
    for hardware in ("flow_rate_mm_per_min", "zone_flow_l_min", "rain_mm_per_tip", "pump_min_watts", "manual_rain_mm"):
        assert hardware not in bundle["numbers"]
    assert bundle["state"]["demand_model"] == "et" and bundle["state"]["mulch_status"] == "bare"
    for individual in ("planting_date_ts", "health_notes", "last_fertilizing_ts"):
        assert individual not in bundle["state"]
    assert bundle["options"][CONF_ROUTINE_TIME] == "05:30:00" and "valve_entity" not in bundle["options"]


@pytest.mark.asyncio
async def test_copy_settings_gives_a_zone_anothers_watering_but_not_its_hardware(hass, fake_valve_services):
    source, target = await _tuned_source(hass)
    ct = _ctl(hass, target)
    flow_before = ct.number("flow_rate_mm_per_min")
    tip_before = ct.number("rain_mm_per_tip")
    await _call(hass, "copy_settings", source_device_id=_device(hass, source), device_id=_device(hass, target))
    ct = _ctl(hass, target)
    assert ct.number("target_weekly_mm") == 31.0 and ct.number("crop_coefficient") == 1.1
    assert ct.number("routine_pulse_count") == 5.0
    assert ct.store.state.demand_model == "et" and ct.store.state.mulch_status == "bare"
    assert ct.number("flow_rate_mm_per_min") == flow_before and ct.number("rain_mm_per_tip") == tip_before
    assert ct.store.state.planting_date_ts is None and ct.store.state.health_notes == ""
    history = _book(hass).main(target.entry_id)["history"]
    assert history[-1]["kind"] == "copied" and history[-1]["data"] == {"source": "Tomatoes"}
    # Copying is not logged as the plant's own edits.
    assert not [h for h in history if h["kind"] == "setting"]
    with pytest.raises(ServiceValidationError):
        await _call(hass, "copy_settings", source_device_id=_device(hass, target), device_id=_device(hass, target))
    with pytest.raises(ServiceValidationError):
        await _call(hass, "copy_settings", device_id=_device(hass, target))


@pytest.mark.asyncio
async def test_a_preset_is_saved_applied_replaced_and_deleted(hass, fake_valve_services, hass_storage):
    source, target = await _tuned_source(hass)
    await _call(hass, "save_preset", name="  Hot  bed ", device_id=_device(hass, source))
    book = await presets.async_get_book(hass)
    assert [p["name"] for p in book.listing()] == ["Hot bed"]
    assert DOMAIN + "_presets" in hass_storage

    await _call(hass, "copy_settings", preset="hot BED", device_id=_device(hass, target))
    assert _ctl(hass, target).number("target_weekly_mm") == 31.0

    # The same name replaces it.
    await _ctl(hass, source).numbers["target_weekly_mm"].async_set_metric_value(20.0)
    await _call(hass, "save_preset", name="Hot bed", device_id=_device(hass, source))
    assert len(book.listing()) == 1 and book.listing()[0]["bundle"]["numbers"]["target_weekly_mm"] == 20.0

    await _call(hass, "delete_preset", name="HOT BED")
    assert book.listing() == []
    with pytest.raises(ServiceValidationError):
        await _call(hass, "delete_preset", name="Hot bed")
    with pytest.raises(ServiceValidationError):
        await _call(hass, "copy_settings", preset="Hot bed", device_id=_device(hass, target))
    with pytest.raises(ServiceValidationError):
        await _call(hass, "save_preset", name="   ", device_id=_device(hass, source))


@pytest.mark.asyncio
async def test_a_new_zone_can_start_as_a_copy_of_another(hass, fake_valve_services):
    source, _ = await _tuned_source(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "zone"})
    field = next(k for k in result["data_schema"].schema if getattr(k, "schema", None) == CONF_START_FROM)
    options = [o["value"] for o in result["data_schema"].schema[field].config["options"]]
    assert options == ["", f"zone:{_zone_id(hass, 'Chilis')}", f"zone:{source.entry_id}"]  # by name

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Peppers", CONF_PLANT: "custom", CONF_ZONE_TYPE: "outdoor", CONF_START_FROM: f"zone:{source.entry_id}"},
    )
    assert result["step_id"] == "entities"
    hass.states.async_set("switch.peppers_valve", "off")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _minimal_entities_input(valve_entity="switch.peppers_valve", csv_path="/tmp/test_zoneflow_peppers.csv")
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CLIMATE: "temperate"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {k.schema: k.default() for k in result["data_schema"].schema}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_START_STATE]["demand_model"] == "et" and data["initial_numbers"]["target_weekly_mm"] == 31.0
    await hass.async_block_till_done()
    new = next(c for c in hass.data[DOMAIN].values() if c.entry.title == "Peppers")
    assert new.number("target_weekly_mm") == 31.0 and new.number("routine_pulse_count") == 5.0
    assert new.store.state.demand_model == "et" and new.store.state.initial_applied
    assert new.number("flow_rate_mm_per_min") != 0.9  # the hardware was not copied
    assert new.store.state.planting_date_ts is None


def _zone_id(hass, title):
    return next(e.entry_id for e in hass.config_entries.async_entries(DOMAIN) if e.title == title)


@pytest.mark.asyncio
async def test_the_first_zone_has_no_start_from_choice(hass, fake_valve_services):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"
    assert CONF_START_FROM not in {getattr(k, "schema", k) for k in result["data_schema"].schema}


@pytest.mark.asyncio
async def test_the_start_settings_are_applied_once(hass, fake_valve_services, hass_storage):
    zone = _zone(hass, **{CONF_START_STATE: {"mulch_status": "bare", "demand_model": "et"}})
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    assert c.store.state.mulch_status == "bare" and c.store.state.initial_applied
    c.store.state.mulch_status = "mulched"  # changed by hand afterwards
    await hass.config_entries.async_reload(zone.entry_id)
    await hass.async_block_till_done()
    assert _ctl(hass, zone).store.state.mulch_status == "mulched"  # a reload does not put it back


@pytest.mark.asyncio
async def test_two_callers_asking_for_the_preset_book_together_both_get_the_saved_presets(hass):
    import asyncio

    from homeassistant.helpers.storage import Store

    saved = {"a": {"id": "a", "name": "Tomato ET drip", "bundle": {}}}
    await Store(hass, 1, "zoneflow_presets").async_save({"presets": saved})
    books = await asyncio.gather(presets.async_get_book(hass), presets.async_get_book(hass))
    assert books[0] is books[1] and books[1].named("tomato et drip") is not None
