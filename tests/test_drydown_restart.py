"""1.7.9: more rain while a dry-down is on starts it again. "Dry-Down Restarts After More Rain"
(default 10 mm, 0 turns it off): that much rain within 24 hours after the dry-down started or
restarted moves its start to now."""
from __future__ import annotations

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import presets, units, visibility
from custom_components.zoneflow.const import DOMAIN, NUMBER_DEFAULTS

from .test_smoke_setup import RAIN_COUNTER, _seed_source_entities, make_entry

KEY = "drydown_restart_rain_mm"
HOUR = 3600.0


async def _zone(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def test_it_starts_at_10_mm_and_is_a_normal_setting():
    assert NUMBER_DEFAULTS[KEY] == 10.0
    assert KEY in units.DEPTH_KEYS and KEY in presets.COPY_NUMBER_KEYS
    assert ("number", KEY) in visibility.RAIN_GAUGE


@pytest.mark.asyncio
async def test_more_rain_than_the_setting_starts_the_dry_down_again(hass):
    c = await _zone(hass)
    now = dt_util.utcnow().timestamp()
    c.store.state.last_significant_rain_ts = now - 2 * HOUR  # a dry-down started 2 hours ago
    c.rain_since = lambda since: 12.0 if since >= now - 86400 else 99.0
    assert c._restart_drydown_on_more_rain(now) is True
    assert c.store.state.last_significant_rain_ts == now


@pytest.mark.asyncio
async def test_less_rain_changes_nothing(hass):
    c = await _zone(hass)
    now = dt_util.utcnow().timestamp()
    started = now - 2 * HOUR
    c.store.state.last_significant_rain_ts = started
    c.rain_since = lambda since: 6.0
    assert c._restart_drydown_on_more_rain(now) is False
    assert c.store.state.last_significant_rain_ts == started


@pytest.mark.asyncio
async def test_it_counts_only_rain_after_the_start_and_within_24_hours(hass):
    c = await _zone(hass)
    now = dt_util.utcnow().timestamp()
    c.store.state.last_significant_rain_ts = now - 3 * 86400  # started 3 days ago
    seen = []
    c.rain_since = lambda since: seen.append(since) or 0.0
    c._restart_drydown_on_more_rain(now)
    assert seen == [now - 86400.0]  # the last 24 hours, not the rain since the start 3 days ago


@pytest.mark.asyncio
async def test_zero_turns_it_off(hass):
    c = await _zone(hass)
    await c.numbers[KEY].async_set_metric_value(0.0)
    now = dt_util.utcnow().timestamp()
    started = now - HOUR
    c.store.state.last_significant_rain_ts = started
    c.rain_since = lambda since: 80.0
    assert c._restart_drydown_on_more_rain(now) is False
    assert c.store.state.last_significant_rain_ts == started


@pytest.mark.asyncio
async def test_nothing_restarts_when_no_dry_down_is_on(hass):
    c = await _zone(hass)
    now = dt_util.utcnow().timestamp()
    c.rain_since = lambda since: 80.0
    assert c._restart_drydown_on_more_rain(now) is False  # never had one
    assert c.store.state.last_significant_rain_ts is None
    c.store.state.last_significant_rain_ts = now - 30 * 86400  # long over
    assert c._restart_drydown_on_more_rain(now) is False


@pytest.mark.asyncio
async def test_a_second_restart_needs_that_much_rain_again(hass):
    c = await _zone(hass)
    now = dt_util.utcnow().timestamp()
    c.store.state.last_significant_rain_ts = now - HOUR
    rain = {"mm": 12.0}
    c.rain_since = lambda since: rain["mm"] if since < now else 0.0  # nothing has fallen since "now"
    assert c._restart_drydown_on_more_rain(now) is True
    assert c._restart_drydown_on_more_rain(now) is False  # the count starts again from now
    assert c.store.state.last_significant_rain_ts == now


@pytest.mark.asyncio
async def test_the_rain_check_itself_restarts_it_and_sends_no_alert(hass):
    c = await _zone(hass)
    hass.states.async_set(RAIN_COUNTER, "100")
    await hass.async_block_till_done()
    now = dt_util.utcnow().timestamp()
    c.store.state.last_significant_rain_ts = now - 2 * HOUR
    c.store.state.rain_threshold_flags = {"24h": True, "4d": True, "7d": True}  # already over, no new crossing
    c.rain_since = lambda since: 15.0
    alerts = []
    c._log_event = lambda **kw: alerts.append(kw)
    c._check_significant_rain()
    await hass.async_block_till_done()
    assert c.store.state.last_significant_rain_ts >= now
    assert alerts == []


@pytest.mark.asyncio
async def test_rain_after_the_routine_dry_down_ended_does_not_block_routine_watering(hass):
    c = await _zone(hass)
    now = dt_util.utcnow().timestamp()
    started = now - 6 * 86400  # routine hold (4 d) over, deep soak hold (8 d) still on
    c.store.state.last_significant_rain_ts = started
    c.rain_since = lambda since: 12.0
    assert c._restart_drydown_on_more_rain(now) is False
    assert c.store.state.last_significant_rain_ts == started


@pytest.mark.asyncio
async def test_a_hand_edit_of_last_significant_rain_is_honored(hass):
    """Setting the date back must not let the storm before the edit restart the dry-down again."""
    from homeassistant.helpers import entity_registry as er

    c = await _zone(hass)
    now = dt_util.utcnow().timestamp()
    reg = er.async_get(hass)
    ent = next(e.entity_id for e in reg.entities.values()
               if e.config_entry_id == c.entry.entry_id and e.entity_id.startswith("datetime.") and e.entity_id.endswith("last_significant_rain"))
    await hass.services.async_call(
        "datetime", "set_value",
        {"entity_id": ent, "datetime": dt_util.utc_from_timestamp(now - 30 * HOUR).isoformat()}, blocking=True,
    )
    assert c.store.state.last_significant_rain_ts == pytest.approx(now - 30 * HOUR, abs=1)
    assert c.store.state.drydown_counted_from_ts >= now - 5
    seen = []
    c.rain_since = lambda since: seen.append(since) or 0.0
    c._restart_drydown_on_more_rain(dt_util.utcnow().timestamp())
    assert seen and seen[0] >= now - 5
