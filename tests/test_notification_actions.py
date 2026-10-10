"""Buttons on phone notifications (1.7.0)."""
from __future__ import annotations

import pytest
from homeassistant.core import ServiceCall

from custom_components.zoneflow import notification_actions as na
from custom_components.zoneflow.const import CONF_NOTIFY_ENTITY

from .test_scenarios_cycles import _history, _set, _zone
from .test_smoke_setup import VALVE


async def _ready(hass, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=3, peaks=(30.5, 30.5, 30.5))
    return controller, clock


def _capture(hass, service):
    calls = []

    async def handler(call: ServiceCall):
        calls.append(call.data)

    hass.services.async_register("notify", service, handler)
    return calls


def _use_notify(controller, entity):
    controller.hass.config_entries.async_update_entry(
        controller.entry, options={**controller.entry.options, CONF_NOTIFY_ENTITY: entity}
    )


@pytest.mark.asyncio
async def test_a_skip_message_to_a_phone_carries_action_buttons(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _ = await _ready(hass, monkeypatch, tmp_path)
    legacy = _capture(hass, "mobile_app_pixel")
    plain = _capture(hass, "send_message")
    monkeypatch.setattr(type(controller), "notify_entity", property(lambda self: "notify.mobile_app_pixel"))
    await controller._log_event(
        event_type="Pre-Irrigation Rain Cancellation", status="Cancelled", target_mm=0.0, deducted_mm=0.0, runtime=0,
        notify_phone=True, message="rain_cancel", params={"cycle": "Routine", "rain": "5 mm"},
    )
    assert plain == [] and len(legacy) == 1
    actions = legacy[0]["data"]["actions"]
    assert [a["title"] for a in actions] == ["Water 10 min", "Snooze today"]
    assert actions[0]["action"] == f"ZONEFLOW|{controller.entry.entry_id}|water"
    assert legacy[0]["data"]["tag"] == f"zoneflow_{controller.entry.entry_id}"


@pytest.mark.asyncio
async def test_other_messages_and_other_phones_get_the_plain_message(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _ = await _ready(hass, monkeypatch, tmp_path)
    legacy = _capture(hass, "mobile_app_pixel")
    plain = _capture(hass, "send_message")
    monkeypatch.setattr(type(controller), "notify_entity", property(lambda self: "notify.mobile_app_pixel"))
    # A message that offers no buttons.
    await controller._log_event(
        event_type="Routine Irrigation Completed", status="Completed", target_mm=1.0, deducted_mm=0.0, runtime=5,
        notify_phone=True, message="routine_done",
        params={"amount": "1 mm", "pulses": 1, "minutes": 5, "next": "", "rain": "0", "rain_note": ""},
    )
    assert legacy == [] and len(plain) == 1
    # A notify target that is not the companion app: plain, even for a skip.
    monkeypatch.setattr(type(controller), "notify_entity", property(lambda self: "notify.family_group"))
    await controller._log_event(
        event_type="Pre-Irrigation Rain Cancellation", status="Cancelled", target_mm=0.0, deducted_mm=0.0, runtime=0,
        notify_phone=True, message="rain_cancel", params={"cycle": "Routine", "rain": "5 mm"},
    )
    assert len(plain) == 2 and legacy == []


@pytest.mark.asyncio
async def test_tapping_the_buttons_waters_snoozes_and_records_a_feed(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock = await _ready(hass, monkeypatch, tmp_path)
    entry_id = controller.entry.entry_id

    async def tap(verb):
        hass.bus.async_fire("mobile_app_notification_action", {"action": f"ZONEFLOW|{entry_id}|{verb}"})
        await hass.async_block_till_done()

    await tap("water")
    assert clock.pulses_for(VALVE) == [10]
    await tap("snooze")
    assert controller.store.state.snooze_date_iso is not None
    assert controller.store.state.last_fertilizing_ts is None
    await tap("fertilized")
    assert controller.store.state.last_fertilizing_ts is not None


@pytest.mark.asyncio
async def test_buttons_of_other_apps_and_stale_buttons_do_nothing(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock = await _ready(hass, monkeypatch, tmp_path)
    for action in ("SOMETHING_ELSE", "ZONEFLOW|nope|water", f"ZONEFLOW|{controller.entry.entry_id}|dance", "ZONEFLOW|x"):
        hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()
    assert clock.pulses == [] and controller.store.state.snooze_date_iso is None
    # A paused zone: the button is refused quietly (it is logged), nothing runs.
    await controller.set_paused(True)
    hass.bus.async_fire("mobile_app_notification_action", {"action": f"ZONEFLOW|{controller.entry.entry_id}|water"})
    await hass.async_block_till_done()
    assert clock.pulses == []
    assert na.build(hass, "e", ("water",))[0]["title"] == "Water 10 min"
