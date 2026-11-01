"""1.8: the small items of the outside review: the area service on an aborted flow, Weather
Underground connections and station lists, a hanging notify service, stale phone buttons."""
from __future__ import annotations

import asyncio
import time

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError

from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow import notification_actions as na
from custom_components.zoneflow import wu
from custom_components.zoneflow.const import DOMAIN

from .test_areas import _boot, _zone
from .test_notification_actions import _ready, _use_notify
from .test_smoke_setup import VALVE


@pytest.mark.asyncio
async def test_an_aborted_area_flow_is_a_readable_error_not_a_key_error(hass, fake_valve_services, monkeypatch):
    zone = _zone(hass)
    await _boot(hass, zone)

    async def aborted(*args, **kwargs):
        return {"type": "abort", "reason": "already_configured"}

    monkeypatch.setattr(hass.config_entries.flow, "async_init", aborted)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "create_area", {"name": "Garden"}, blocking=True)


class _Response:
    def __init__(self, status, body, log):
        self.status, self._body, self._log = status, body, log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self._log.append("released")

    async def json(self, content_type=None):
        return self._body


class _Session:
    def __init__(self, status=200, body=None):
        self.status, self.body, self.log = status, body or {}, []

    def get(self, url, params=None):
        return _Response(self.status, self.body, self.log)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 204, 401, 404, 500])
async def test_every_wu_response_is_released(hass, monkeypatch, status):
    session = _Session(status, {"ok": 1})
    monkeypatch.setattr(wu, "async_get_clientsession", lambda hass: session)
    try:
        await wu._get_json(hass, "https://x", {})
    except (wu.InvalidKey, wu.CannotConnect):
        pass
    assert session.log == ["released"]


@pytest.mark.asyncio
async def test_more_than_ten_stations_without_names_are_all_listed(hass, monkeypatch):
    hass.config.latitude, hass.config.longitude = 9.5, 100.0
    n = 14
    body = {"location": {
        "stationId": [f"I{i}" for i in range(n)],
        "latitude": [9.5 + i / 1000 for i in range(n)],
        "longitude": [100.0] * n,
    }}
    monkeypatch.setattr(wu, "async_get_clientsession", lambda hass: _Session(200, body))
    stations = await wu.async_nearby_stations(hass, "key")
    assert len(stations) == n and stations[0]["name"] == "I0"


@pytest.mark.asyncio
async def test_a_notify_service_that_hangs_does_not_hold_up_the_logging(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _ = await _ready(hass, monkeypatch, tmp_path)
    monkeypatch.setattr(controller_module, "NOTIFY_TIMEOUT_SECONDS", 0.2)
    _use_notify(controller, "notify.slow_phone")

    async def hang(call: ServiceCall):
        await asyncio.sleep(30)

    hass.services.async_register("notify", "send_message", hang)
    started = time.monotonic()
    await controller._log_event(
        event_type="Test", status="x", target_mm=0.0, deducted_mm=0.0, runtime=0,
        notify_phone=True, message="rain_cancel", params={"cycle": "Routine", "rain": "5 mm"},
    )
    assert time.monotonic() - started < 5


@pytest.mark.asyncio
async def test_an_old_water_button_does_nothing_but_a_fresh_or_unstamped_one_works(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock = await _ready(hass, monkeypatch, tmp_path)
    entry_id = controller.entry.entry_id

    async def tap(action):
        hass.bus.async_fire("mobile_app_notification_action", {"action": action})
        await hass.async_block_till_done()

    stale = f"ZONEFLOW|{entry_id}|water|{int(time.time()) - na.WATER_BUTTON_MAX_AGE_SECONDS - 60}"
    await tap(stale)
    await tap(f"ZONEFLOW|{entry_id}|water|garbage")
    assert clock.pulses == []
    await tap(na.action_id(entry_id, "water"))
    assert sum(clock.pulses_for(VALVE)) == pytest.approx(10)
