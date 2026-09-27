"""Fertilizing: Next Fertilizing = Last Fertilizing + Fertilizing Interval,
the "Fertilized Today" button records a feed, and one phone reminder goes
out on the due date (not while the zone is paused)."""
from datetime import datetime, timedelta

import pytest
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import DOMAIN, FERTILIZE_REMINDER_HOUR, FERTILIZING_INTERVAL_OPTIONS

from .test_smoke_setup import PUMP, VALVE, make_entry, schedule_clear_of_now


def test_next_date():
    last = datetime(2026, 1, 31, 10, 0)
    assert calc.next_fertilizing(last, "2w") == datetime(2026, 2, 14, 10, 0)
    assert calc.next_fertilizing(last, "1") == datetime(2026, 2, 28, 10, 0)  # no 31 Feb
    assert calc.next_fertilizing(datetime(2027, 12, 31), "2") == datetime(2028, 2, 29)  # leap year
    assert calc.next_fertilizing(datetime(2026, 11, 15), "3") == datetime(2027, 2, 15)
    assert calc.next_fertilizing(datetime(2026, 5, 5), "12") == datetime(2027, 5, 5)
    # The original month options are still there (saved choices keep working).
    assert {str(m) for m in range(1, 13)} <= set(FERTILIZING_INTERVAL_OPTIONS)


async def _zone(hass, tmp_path):
    notes = []

    async def _notify(call):
        notes.append(call.data)

    hass.services.async_register("notify", "send_message", _notify)
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    entry = make_entry(hass, csv_path=str(tmp_path / "f.csv"), notify_entity="notify.phone", **schedule_clear_of_now())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id], notes


def _entity(hass, domain, suffix):
    return next(e for e in hass.states.async_entity_ids(domain) if e.endswith(suffix))


def _next_reminder_time():
    now = dt_util.now()
    at = now.replace(hour=FERTILIZE_REMINDER_HOUR, minute=0, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


@pytest.mark.asyncio
async def test_the_button_sets_the_date_and_the_next_one_follows(hass, fake_valve_services, tmp_path):
    controller, _ = await _zone(hass, tmp_path)
    sensor = _entity(hass, "sensor", "_next_fertilizing")
    assert hass.states.get(sensor).state == "unknown"  # no feed recorded yet

    await hass.services.async_call("button", "press", {"entity_id": _entity(hass, "button", "_fertilized_today")}, blocking=True)
    await hass.async_block_till_done()
    today = dt_util.now().date()
    last = hass.states.get(_entity(hass, "datetime", "_last_fertilizing")).state
    assert dt_util.as_local(dt_util.parse_datetime(last)).date() == today
    expected = calc.next_fertilizing(dt_util.now(), "3").date()  # default: 3 months
    assert hass.states.get(sensor).state == expected.isoformat()
    assert hass.states.get(sensor).attributes["due"] is False

    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": _entity(hass, "select", "_fertilizing_interval"), "option": "2w"}, blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == (today + timedelta(weeks=2)).isoformat()


@pytest.mark.asyncio
async def test_one_reminder_on_the_due_date(hass, fake_valve_services, tmp_path):
    controller, notes = await _zone(hass, tmp_path)
    state = controller.store.state
    state.fertilizing_interval_months = "2w"
    state.last_fertilizing_ts = (dt_util.utcnow() - timedelta(days=15)).timestamp()  # due yesterday
    assert controller.fertilizing_due()

    at = _next_reminder_time()
    async_fire_time_changed(hass, dt_util.as_utc(at) + timedelta(seconds=1))
    await hass.async_block_till_done()
    feed = [n for n in notes if "fertiliz" in n["title"].lower()]
    assert len(feed) == 1 and "Test Zone" in feed[0]["title"]

    await controller._on_fertilize_check()  # the next morning's check
    assert len([n for n in notes if "fertiliz" in n["title"].lower()]) == 1  # once per feed

    await controller.fertilized_today()  # done: nothing due any more
    assert not controller.fertilizing_due()
    assert "Fertilized" in (tmp_path / "f.csv").read_text()


@pytest.mark.asyncio
async def test_no_reminder_before_the_due_date_or_while_paused(hass, fake_valve_services, tmp_path):
    controller, notes = await _zone(hass, tmp_path)
    state = controller.store.state
    state.fertilizing_interval_months = "1"
    state.last_fertilizing_ts = dt_util.utcnow().timestamp()  # due in a month
    await controller._on_fertilize_check()
    state.last_fertilizing_ts = (dt_util.utcnow() - timedelta(days=40)).timestamp()
    state.paused = True
    await controller._on_fertilize_check()
    assert not [n for n in notes if "fertiliz" in n["title"].lower()]
    state.paused = False
    await controller._on_fertilize_check()
    assert len([n for n in notes if "fertiliz" in n["title"].lower()]) == 1
