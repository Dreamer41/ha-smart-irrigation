"""The valve test that ends zone setup (1.7.4): an optional step that opens the valve
for a moment and says whether it answered and closed, before the zone is added."""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.zoneflow import config_flow
from custom_components.zoneflow.const import (
    CONF_IRRIGATION_METHOD,
    CONF_QUICK_SETUP,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
)

from .test_suggest import _house

VALVE = "switch.sprinkler_valve"
FLOW = {"emitters": 10, "emitter_flow": 2.0, "area": 2.0}


@pytest.fixture(autouse=True)
def _fast_test(monkeypatch):
    monkeypatch.setattr(config_flow, "VALVE_TEST_HOLD_SECONDS", 0)
    monkeypatch.setattr(config_flow, "VALVE_TEST_WAIT_SECONDS", 0.5)


async def _to_the_last_step(hass):
    _house(hass)
    hass.states.async_set(VALVE, "off")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Tomato bed", "plant": "tomatoes", CONF_ZONE_TYPE: "outdoor", CONF_QUICK_SETUP: True},
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "drip", **FLOW}
    )


@pytest.mark.asyncio
async def test_setup_ends_with_the_valve_test_and_the_valve_answers(hass, fake_valve_services, valve_test_on):
    result = await _to_the_last_step(hass)
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "test_valve"
    assert result["description_placeholders"]["valve"] == VALVE
    assert hass.config_entries.async_entries(DOMAIN) == []  # not added yet
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"test": True})
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "valve_result"
    assert "answered" in result["description_placeholders"]["result"]
    assert hass.states.get(VALVE).state == "off"  # told to close
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY and result["title"] == "Tomato bed"


@pytest.mark.asyncio
async def test_the_test_can_be_skipped(hass, fake_valve_services, valve_test_on):
    result = await _to_the_last_step(hass)
    assert result["step_id"] == "test_valve"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"test": False})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert hass.states.get(VALVE).state == "off"  # never opened


@pytest.mark.asyncio
async def test_a_valve_that_never_answers_is_said_so_and_the_zone_is_still_added(
    hass, fake_valve_services, valve_test_on
):
    result = await _to_the_last_step(hass)
    calls = []

    async def silent_on(call):
        calls.append(("on", call.data["entity_id"]))  # the device never reports open

    async def off(call):
        hass.states.async_set(call.data["entity_id"], "off")
        calls.append(("off", call.data["entity_id"]))

    hass.services.async_register("switch", "turn_on", silent_on)
    hass.services.async_register("switch", "turn_off", off)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"test": True})
    assert "did not answer" in result["description_placeholders"]["result"]
    assert ("off", VALVE) in calls  # and it was still told to close
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_a_valve_that_will_not_close_is_called_out(hass, fake_valve_services, valve_test_on):
    result = await _to_the_last_step(hass)
    offs = []

    async def on(call):
        hass.states.async_set(call.data["entity_id"], "on")

    async def stuck_off(call):
        offs.append(call.data["entity_id"])  # the state stays on

    hass.services.async_register("switch", "turn_on", on)
    hass.services.async_register("switch", "turn_off", stuck_off)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"test": True})
    assert "did not report closed" in result["description_placeholders"]["result"]
    assert len(offs) == 2  # told twice


@pytest.mark.asyncio
async def test_an_unavailable_valve_is_not_tested(hass, fake_valve_services, valve_test_on):
    result = await _to_the_last_step(hass)
    hass.states.async_set(VALVE, "unavailable")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"test": True})
    assert "unavailable" in result["description_placeholders"]["result"]
    assert hass.states.get(VALVE).state == "unavailable"


def test_a_zone_without_a_valve_has_no_valve_test(valve_test_on):
    assert config_flow._offers_valve_test({CONF_VALVE_ENTITY: "switch.v"}) is True
    assert config_flow._offers_valve_test({}) is False


@pytest.mark.asyncio
async def test_a_device_that_raises_a_raw_error_is_still_closed(hass, fake_valve_services, valve_test_on):
    result = await _to_the_last_step(hass)
    offs = []

    async def open_then_fail(call):
        hass.states.async_set(call.data["entity_id"], "on")
        raise TimeoutError("no answer from the device")

    async def off(call):
        hass.states.async_set(call.data["entity_id"], "off")
        offs.append(call.data["entity_id"])

    hass.services.async_register("switch", "turn_on", open_then_fail)
    hass.services.async_register("switch", "turn_off", off)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"test": True})
    assert result["step_id"] == "valve_result"  # not "Unknown error"
    assert offs == [VALVE] and hass.states.get(VALVE).state == "off"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_a_valve_that_is_already_open_is_left_alone(hass, fake_valve_services, valve_test_on):
    result = await _to_the_last_step(hass)
    hass.states.async_set(VALVE, "on")  # someone is watering by hand
    calls = []

    async def record(call):
        calls.append(call.service)

    hass.services.async_register("switch", "turn_on", record)
    hass.services.async_register("switch", "turn_off", record)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"test": True})
    assert "already open" in result["description_placeholders"]["result"]
    assert calls == [] and hass.states.get(VALVE).state == "on"
