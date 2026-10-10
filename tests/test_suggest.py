"""Likely entities in the setup form, and the step counter (1.7.0)."""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er

from custom_components.zoneflow import suggest
from custom_components.zoneflow.const import (
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
)


def _house(hass):
    hass.states.async_set("sensor.garden_rain_gauge", "3.2", {"device_class": "precipitation", "friendly_name": "Garden rain", "unit_of_measurement": "mm"})
    hass.states.async_set("sensor.outdoor_temperature", "29.5", {"device_class": "temperature", "friendly_name": "Outdoor temperature", "unit_of_measurement": "°C"})
    hass.states.async_set("sensor.living_room_temperature", "24", {"device_class": "temperature", "friendly_name": "Living room temperature"})
    hass.states.async_set("sensor.fridge_temperature", "4", {"device_class": "temperature", "friendly_name": "Fridge temperature"})
    hass.states.async_set("switch.sprinkler_valve", "off", {"friendly_name": "Sprinkler valve"})
    hass.states.async_set("switch.kitchen_light", "off", {"friendly_name": "Kitchen light"})
    hass.states.async_set("weather.home", "sunny", {"friendly_name": "Home"})
    hass.states.async_set("notify.mobile_app_pixel", "unknown", {"friendly_name": "Pixel"})
    hass.states.async_set("notify.family_group", "unknown")
    hass.states.async_set("sensor.soil_probe", "41", {"device_class": "moisture", "friendly_name": "Soil probe"})
    hass.states.async_set("sensor.hall_humidity", "50", {"device_class": "humidity", "friendly_name": "Hall humidity"})


def test_the_likely_ones_are_found_ranked_and_the_wrong_ones_left_out(hass):
    _house(hass)
    found = suggest.find(hass)
    assert [c["entity_id"] for c in found["rain"]] == ["sensor.garden_rain_gauge"]
    assert [c["entity_id"] for c in found["temperature"]] == ["sensor.outdoor_temperature"]  # not the room or the fridge
    assert [c["entity_id"] for c in found["valve"]] == ["switch.sprinkler_valve"]
    assert [c["entity_id"] for c in found["weather"]] == ["weather.home"]
    assert [c["entity_id"] for c in found["notify"]] == ["notify.mobile_app_pixel"]  # the companion app only
    assert [c["entity_id"] for c in found["soil"]] == ["sensor.soil_probe"]
    assert found["rain"][0]["value"] == "3.2 mm" and found["rain"][0]["name"] == "Garden rain"


def test_only_a_clear_single_match_is_filled_in(hass):
    _house(hass)
    defaults = suggest.defaults_from(suggest.find(hass))
    assert defaults[CONF_RAIN_COUNTER_ENTITY] == "sensor.garden_rain_gauge"
    assert defaults[CONF_OUTDOOR_TEMP_ENTITY] == "sensor.outdoor_temperature"
    assert defaults[CONF_WEATHER_ENTITY] == "weather.home" and defaults[CONF_NOTIFY_ENTITY] == "notify.mobile_app_pixel"
    assert CONF_VALVE_ENTITY not in defaults  # a valve is only listed, never filled in
    # Two weather entities: nothing is guessed.
    hass.states.async_set("weather.office", "rainy")
    assert CONF_WEATHER_ENTITY not in suggest.defaults_from(suggest.find(hass))
    # What another zone already uses is not offered again.
    taken = suggest.defaults_from(suggest.find(hass), {"sensor.garden_rain_gauge"})
    assert CONF_RAIN_COUNTER_ENTITY not in taken


def test_the_list_under_the_form_reads_plainly(hass):
    _house(hass)
    text = suggest.describe(hass, suggest.find(hass))
    assert text.startswith("Likely ones found in your Home Assistant:")
    assert "Rain gauge: Garden rain (3.2 mm)" in text and "Outdoor temperature: Outdoor temperature (29.5 °C)" in text
    assert "Phone: Pixel" in text and "fridge" not in text.lower()
    assert suggest.describe(hass, {role: [] for role in suggest.ROLES}) == ""


def test_zoneflows_own_entities_are_never_suggested(hass):
    registry = er.async_get(hass)
    own = registry.async_get_or_create("sensor", DOMAIN, "x_rain_today", suggested_object_id="tomatoes_rain_today")
    hass.states.async_set(own.entity_id, "1.0", {"device_class": "precipitation", "friendly_name": "Tomatoes Rain Today"})
    assert suggest.find(hass)["rain"] == []


@pytest.mark.asyncio
async def test_the_setup_form_fills_in_the_clear_ones_and_counts_the_steps(hass, fake_valve_services):
    _house(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ZONE_NAME: "Lawn", "plant": "lawn", CONF_ZONE_TYPE: "outdoor"}
    )
    assert result["step_id"] == "entities"
    suggested = {
        getattr(k, "schema", k): (k.description or {}).get("suggested_value") for k in result["data_schema"].schema
        if hasattr(k, "description")
    }
    assert suggested[CONF_RAIN_COUNTER_ENTITY] == "sensor.garden_rain_gauge"
    assert suggested[CONF_OUTDOOR_TEMP_ENTITY] == "sensor.outdoor_temperature"
    placeholders = result["description_placeholders"]
    assert placeholders["progress"] == "Step 2 of 4" and "Garden rain (3.2 mm)" in placeholders["suggestions"]
