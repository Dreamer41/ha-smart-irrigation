"""Nursery plants (1.7.1): follow a plant towards "ready to move" -- its stage
from the planting date, one phone message when it is ready, and "established"
once it has been moved."""
from __future__ import annotations

from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.zoneflow import plant_api
from custom_components.zoneflow.const import CONF_PLANT, DOMAIN, PLANT_READY_DAYS
from custom_components.zoneflow.plants import STAGE_ESTABLISHED, STAGE_READY, STAGE_SEED, STAGE_SEEDLING, stage_of

from .test_greenhouse_crops import VALVE_B
from .test_plants import _book, _boot, _ctl, _zone

DAY = 86400.0


def _plant(days=42, **extra):
    return {"ready_days": days, **extra}


def test_a_plant_that_is_not_followed_has_no_stage():
    assert stage_of({}, 1000.0, 2000.0) is None
    assert stage_of({"ready_days": 0}, 1000.0, 2000.0) is None


def test_the_stage_follows_the_days_since_planting():
    now = 100 * DAY
    stage = lambda age: stage_of(_plant(42), now - age * DAY, now)["stage"]  # noqa: E731
    assert stage(1) == STAGE_SEED
    assert stage(10) == STAGE_SEEDLING
    assert stage(41) == STAGE_SEEDLING
    assert stage(42) == STAGE_READY
    assert stage(80) == STAGE_READY
    assert stage_of(_plant(42), now - 30 * DAY, now)["days_left"] == 12


def test_without_a_planting_date_a_followed_plant_is_a_seed_with_no_count():
    assert stage_of(_plant(42), None, 1000.0) == {"stage": STAGE_SEED, "days_left": None, "ready_days": 42}


def test_a_moved_plant_is_established():
    assert stage_of(_plant(42, transplanted_ts=5.0), 0.0, 400 * DAY)["stage"] == STAGE_ESTABLISHED


def test_the_usual_days_are_for_types_that_are_raised_from_seed():
    assert PLANT_READY_DAYS["tomatoes"] == 42 and "lawn" not in PLANT_READY_DAYS


def _device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)}).id


async def _call(hass, service, **data):
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_a_record_is_followed_from_its_planting_date_and_messages_once(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    c.notify_plant_ready = AsyncMock()
    day = (dt_util.now() - __import__("datetime").timedelta(days=50)).date()
    await _call(hass, "add_plant", name="Basil", plant_type="herbs", ready_days=35, planted=day.isoformat(), device_id=_device(hass, zone))
    basil = next(p for p in _book(hass).in_zone(zone.entry_id) if p["name"] == "Basil")
    assert basil["ready_days"] == 35

    await c.plants.async_check_ready()
    await c.plants.async_check_ready()  # a second look says nothing more
    c.notify_plant_ready.assert_called_once_with("Basil")
    row = next(r for r in c.plants.summary() if r["name"] == "Basil")
    assert row["stage"] == "ready" and row["days_left"] == 0


@pytest.mark.asyncio
async def test_the_main_plant_uses_the_zones_planting_date(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    main = _book(hass).main(zone.entry_id)
    await _call(hass, "set_plant_ready", plant_id=main["id"], ready_days=20)
    assert c.plants.summary()[0]["stage"] == "seed"  # no planting date yet
    c.store.state.planting_date_ts = dt_util.utcnow().timestamp() - 25 * DAY
    assert c.plants.summary()[0]["stage"] == "ready"


@pytest.mark.asyncio
async def test_setting_the_planting_date_from_the_service(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    main = _book(hass).main(zone.entry_id)
    await _call(hass, "set_plant_ready", plant_id=main["id"], ready_days=10, planted="2024-03-01")
    assert dt_util.as_local(dt_util.utc_from_timestamp(c.store.state.planting_date_ts)).date().isoformat() == "2024-03-01"


@pytest.mark.asyncio
async def test_without_days_the_types_usual_number_is_used_and_zero_stops(hass, fake_valve_services):
    zone = _zone(hass, **{CONF_PLANT: "tomatoes"})
    await _boot(hass, zone)
    main = _book(hass).main(zone.entry_id)
    await _call(hass, "set_plant_ready", plant_id=main["id"])
    assert main["ready_days"] == 42  # tomatoes
    await _call(hass, "set_plant_ready", plant_id=main["id"], ready_days=0)
    assert "ready_days" not in main
    with pytest.raises(Exception):
        await _call(hass, "set_plant_ready", plant_id=main["id"], ready_days=1000)


@pytest.mark.asyncio
async def test_moving_a_followed_plant_makes_it_established_and_new_days_start_again(hass, fake_valve_services):
    a, b = _zone(hass), _zone(hass, "Bed", VALVE_B)
    await _boot(hass, a, b)
    ca = _ctl(hass, a)
    ca.notify_plant_ready = AsyncMock()
    await _call(hass, "add_plant", name="Seedling", plant_type="tomatoes", ready_days=10, device_id=_device(hass, a))
    seedling = next(p for p in _book(hass).in_zone(a.entry_id) if p["name"] == "Seedling")
    await _call(hass, "move_plant", plant_id=seedling["id"], old_main="extra", device_id=_device(hass, b))
    row = next(r for r in _ctl(hass, b).plants.summary() if r["name"] == "Seedling")
    assert row["stage"] == "established"

    seedling["ready_notified"] = True
    await _call(hass, "set_plant_ready", plant_id=seedling["id"], ready_days=14)
    assert "ready_notified" not in seedling and "transplanted_ts" not in seedling


@pytest.mark.asyncio
async def test_the_card_gets_the_stage_the_default_and_the_planting_date(hass, fake_valve_services):
    zone = _zone(hass, **{CONF_PLANT: "tomatoes"})
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    main = _book(hass).main(zone.entry_id)
    c.store.state.planting_date_ts = dt_util.utcnow().timestamp() - 10 * DAY
    fields = plant_api._ready_fields(main, c)
    assert fields["ready_days_default"] == 42 and fields["planted"] and "stage" not in fields
    main["ready_days"] = 42
    fields = plant_api._ready_fields(main, c)
    assert fields["stage"] == "seedling" and fields["days_left"] == 32


@pytest.mark.asyncio
async def test_the_phone_message_names_the_plant(hass, fake_valve_services, monkeypatch):
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    sent = []

    async def log_event(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(c, "_log_event", log_event)
    await c.notify_plant_ready("Basil")
    assert sent[0]["message"] == "plant_ready" and sent[0]["params"]["plant"] == "Basil" and sent[0]["notify_phone"]


@pytest.mark.asyncio
async def test_the_planting_date_the_card_gets_is_the_local_day(hass, fake_valve_services):
    await hass.config.async_set_time_zone("Asia/Bangkok")  # local midnight is the day before in UTC
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    main = _book(hass).main(zone.entry_id)
    await _call(hass, "set_plant_ready", plant_id=main["id"], ready_days=10, planted="2026-09-20")
    assert plant_api._ready_fields(main, c)["planted"] == "2026-09-20"
