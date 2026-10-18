"""Check my setup (1.7.0): a plain checklist for a zone."""
from __future__ import annotations

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.zoneflow import plant_api, setup_check
from custom_components.zoneflow.const import CONF_NOTIFY_ENTITY, CONF_WEATHER_ENTITY, DOMAIN

from .test_plants import _boot, _ctl, _zone
from .test_smoke_setup import OUTDOOR_TEMP, RAIN_COUNTER, VALVE


def _by_id(items):
    return {i["id"]: i for i in items}


@pytest.mark.asyncio
async def test_a_healthy_zone_checks_out_and_problems_come_first(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE, **{CONF_WEATHER_ENTITY: "weather.home"})
    hass.states.async_set("weather.home", "sunny")
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(OUTDOOR_TEMP, "29.5", {"unit_of_measurement": "°C"})
    items = setup_check.run_checks(c)
    by = _by_id(items)
    assert by["valve"]["level"] == "ok" and "switch.watering" not in by["valve"]["text"] or by["valve"]["level"] == "ok"
    assert by["rain"]["level"] == "ok" and by["temperature"]["text"] == "Outdoor temperature is 29.5 °C."
    assert by["weather"]["level"] == "ok"
    # The example flow rate and no litres: a warning and an advice, first in the list.
    assert by["flow"]["level"] == "warn" and by["flow"]["action"] == "calibrate"
    assert by["volume"]["level"] == "info" and by["last"]["level"] == "info"
    levels = [i["level"] for i in items]
    assert levels == sorted(levels, key={"fail": 0, "warn": 1, "info": 2, "ok": 3}.get)
    assert setup_check.summary(items) == "warn"

    # Calibrated, Zone Flow set: both are fine.
    await c.numbers["flow_rate_mm_per_min"].async_set_metric_value(0.42)
    await c.numbers["zone_flow_l_min"].async_set_metric_value(20.0)
    by = _by_id(setup_check.run_checks(c))
    assert by["flow"]["level"] == "ok" and by["volume"]["level"] == "ok"


@pytest.mark.asyncio
async def test_a_dead_valve_and_sensors_are_reported_plainly(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE, **{CONF_NOTIFY_ENTITY: "notify.gone"})
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    hass.states.async_set(VALVE, "unavailable")
    hass.states.async_set(RAIN_COUNTER, "unavailable")
    hass.states.async_set(OUTDOOR_TEMP, "unknown")
    by = _by_id(setup_check.run_checks(c))
    assert by["valve"]["level"] == "fail" and "not available" in by["valve"]["text"]
    assert by["rain"]["level"] == "fail" and by["temperature"]["level"] == "warn"
    assert by["notify"]["level"] == "warn"
    assert setup_check.summary(setup_check.run_checks(c)) == "fail"


@pytest.mark.asyncio
async def test_a_zone_without_sensors_and_a_paused_zone(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE, **{"rain_counter_entity": None, "outdoor_temp_entity": None})
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    by = _by_id(setup_check.run_checks(c))
    assert by["rain"]["level"] == "info" and by["temperature"]["level"] == "warn" and by["weather"]["level"] == "info"
    assert by["notify"]["level"] == "info"
    await c.set_paused(True)
    by = _by_id(setup_check.run_checks(c))
    assert by["paused"]["level"] == "warn"


@pytest.mark.asyncio
async def test_the_last_watering_and_an_overdue_one(hass, fake_valve_services):
    import homeassistant.util.dt as dt_util

    zone = _zone(hass, valve=VALVE)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 86400
    assert _by_id(setup_check.run_checks(c))["last"]["level"] == "ok"
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 40 * 86400
    by = _by_id(setup_check.run_checks(c))
    assert by["last"]["level"] == "warn" and "40 days" in by["last"]["text"]


@pytest.mark.asyncio
async def test_the_card_can_ask_for_the_check(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE)
    await _boot(hass, zone)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, zone.entry_id)})

    class Connection:
        result = error = None

        def send_result(self, msg_id, result):
            self.result = result

        def send_error(self, msg_id, code, message):
            self.error = code

    connection = Connection()
    plant_api.ws_check(hass, connection, {"id": 1, "type": "zoneflow/check", "device_id": device.id})
    await hass.async_block_till_done()
    assert connection.result["zone"] == "Tomatoes" and connection.result["level"] in ("warn", "fail", "info", "ok")
    assert {i["id"] for i in connection.result["items"]} >= {"valve", "rain", "flow"}
    missing = Connection()
    plant_api.ws_check(hass, missing, {"id": 2, "type": "zoneflow/check", "device_id": "nope"})
    await hass.async_block_till_done()
    assert missing.error == "not_found"


# --- ignoring a warning (1.7.4) ---------------------------------------------------
class _Admin:
    def __init__(self, is_admin=True):
        self.user = type("User", (), {"is_admin": is_admin})()
        self.result = self.error = None

    def send_result(self, msg_id, result):
        self.result = result

    def send_error(self, msg_id, code, message):
        self.error = code


async def _ignore(hass, zone, item_id, ignore, admin=True):
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, zone.entry_id)})
    connection = _Admin(admin)
    # Through the command's real schema, as Home Assistant checks it: "id" is the message id (an int).
    message = plant_api.ws_check_ignore._ws_schema(
        {"id": 7, "type": "zoneflow/check_ignore", "device_id": device.id, "item_id": item_id, "ignore": ignore}
    )
    plant_api.ws_check_ignore(hass, connection, message)
    await hass.async_block_till_done()
    return connection


@pytest.mark.asyncio
async def test_a_warning_can_be_ignored_and_shown_again(hass, fake_valve_services):
    from homeassistant.helpers import issue_registry as ir

    zone = _zone(hass, valve=VALVE)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    from custom_components.zoneflow import issues

    issues.async_check(c)
    registry = ir.async_get(hass)
    issue_id = f"{zone.entry_id}_flow_rate_default"
    assert registry.async_get_issue(DOMAIN, issue_id) is not None  # the example flow rate: a warning and a repair
    assert _by_id(setup_check.run_checks(c))["flow"]["level"] == "warn"
    before = setup_check.summary(setup_check.run_checks(c))
    assert before == "warn"

    done = await _ignore(hass, zone, "flow", True)
    assert done.error is None
    flow = {i["id"]: i for i in done.result["items"]}["flow"]
    assert flow["ignored"] is True and flow["level"] == "warn"  # still listed, as a warning
    order = {"fail": 0, "warn": 1, "info": 2, "ok": 3}
    counted = [i["level"] for i in done.result["items"] if not i["ignored"]]
    assert done.result["level"] == min(counted, key=order.get)  # it no longer counts
    assert setup_check.summary([{"level": "warn", "ignored": True}]) == "ok"
    assert registry.async_get_issue(DOMAIN, issue_id) is None  # and its Repairs notice is gone
    assert c.store.state.check_ignored == ["flow"]
    ordered = [i["id"] for i in done.result["items"]]
    assert ordered.index("flow") > ordered.index("notify")  # ignored ones go last

    shown = await _ignore(hass, zone, "flow", False)
    assert {i["id"]: i for i in shown.result["items"]}["flow"]["ignored"] is False
    assert shown.result["level"] == "warn"
    assert registry.async_get_issue(DOMAIN, issue_id) is not None  # the repair is back


@pytest.mark.asyncio
async def test_only_a_warning_can_be_ignored_and_only_by_an_administrator(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    hass.states.async_set(VALVE, "unavailable")  # a failure
    assert _by_id(setup_check.run_checks(c))["valve"]["ignorable"] is False
    refused = await _ignore(hass, zone, "valve", True)
    assert refused.error == "not_ignorable" and c.store.state.check_ignored == []
    unknown = await _ignore(hass, zone, "nonsense", True)
    assert unknown.error == "not_ignorable"
    from homeassistant.exceptions import Unauthorized

    with pytest.raises(Unauthorized):
        await _ignore(hass, zone, "flow", True, admin=False)
    assert c.store.state.check_ignored == []  # a non-administrator changed nothing


@pytest.mark.asyncio
async def test_an_ignored_warning_that_goes_away_comes_back_as_new_if_it_returns(hass, fake_valve_services):
    zone = _zone(hass, valve=VALVE)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    await _ignore(hass, zone, "flow", True)
    await c.numbers["flow_rate_mm_per_min"].async_set_metric_value(0.42)  # calibrated: the warning is gone
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, zone.entry_id)})
    connection = type("C", (), {"result": None, "send_result": lambda self, i, r: setattr(self, "result", r), "send_error": lambda *a: None})()
    plant_api.ws_check(hass, connection, {"id": 1, "type": "zoneflow/check", "device_id": device.id})
    await hass.async_block_till_done()
    assert c.store.state.check_ignored == []  # forgotten
    await c.numbers["flow_rate_mm_per_min"].async_set_metric_value(1.0)  # back to the example value
    assert _by_id(setup_check.run_checks(c))["flow"]["ignored"] is False  # a new warning
