"""Why? (1.7.0): the numbers behind a zone's next watering, in plain words."""
from __future__ import annotations

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.zoneflow import plant_api, why
from custom_components.zoneflow.const import DOMAIN

from .test_plants import _boot, _ctl, _zone
from .test_smoke_setup import VALVE


@pytest.mark.asyncio
async def test_the_explanation_lists_method_target_rain_and_what_it_would_water(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    c.store.state.rain_day_history_mm = [0.0, 12.0] + [0.0] * 8
    items = {i["id"]: i["text"] for i in why.explain(c)}
    assert items["method"].startswith("Watering method: temperature tiers")
    assert "Temperature used:" in items["temperature"] and "week." in items["temperature"]
    assert items["target"].startswith("Weekly target: ") and "mm" in items["target"]
    assert "Rain credit" in items["rain"] and "If it watered now" in items["needed"]
    assert "scale" not in items and "soil" not in items and "forecast" not in items
    assert items["last"] == c.status()["text"]


@pytest.mark.asyncio
async def test_growth_ramp_and_forecast_skips_and_the_probe_show_up(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE, weather_entity="weather.home", soil_moisture_entity="sensor.probe")
    hass.states.async_set("weather.home", "sunny")
    hass.states.async_set("sensor.probe", "15")
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    import homeassistant.util.dt as dt_util

    c.store.state.growth_ramp_profile_override = "fast_annual"  # a young plant: less water
    c.store.state.planting_date_ts = dt_util.utcnow().timestamp() - 5 * 86400
    c.store.state.forecast_routine_skip_count = 2
    items = {i["id"]: i["text"] for i in why.explain(c)}
    assert "scaled to" in items["scale"] and "Rain was forecast" in items["forecast"]
    assert items["soil"].startswith("Soil moisture 15 %")


@pytest.mark.asyncio
async def test_a_zone_without_a_valve_has_nothing_to_explain(hass, fake_valve_services):
    from .test_zone_types import _climate_only_entry, _seed

    await _seed(hass)
    house = _climate_only_entry(hass)
    await _boot(hass, house)
    assert why.explain(_ctl(hass, house)) == []


@pytest.mark.asyncio
async def test_the_card_can_ask_why(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE)
    await _boot(hass, zone)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, zone.entry_id)})

    class Connection:
        result = error = None

        def send_result(self, msg_id, result):
            self.result = result

        def send_error(self, msg_id, code, message):
            self.error = code

    ok, bad = Connection(), Connection()
    plant_api.ws_why(hass, ok, {"id": 1, "type": "zoneflow/why", "device_id": device.id})
    plant_api.ws_why(hass, bad, {"id": 2, "type": "zoneflow/why", "device_id": "nope"})
    await hass.async_block_till_done()
    assert {i["id"] for i in ok.result["items"]} >= {"method", "target", "last"} and bad.error == "not_found"
