"""1.8 review fixes: sun-relative schedules run on the event loop, the stuck-valve alert survives a
failing close, and a busy zone is not reloaded by a settings copy or the Deep Soak switch."""
from __future__ import annotations

import pytest
from homeassistant.core import HassJob, HassJobType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.zoneflow import presets
from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow.const import CONF_DEEP_SOAK_ENABLED, DOMAIN, SUN_MODE_AFTER_SUNRISE, SUN_MODE_BEFORE_SUNSET
from datetime import time as dt_time

from .test_smoke_setup import _seed_source_entities, make_entry


async def _zone(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,fn", [(SUN_MODE_AFTER_SUNRISE, "async_track_sunrise"), (SUN_MODE_BEFORE_SUNSET, "async_track_sunset")])
async def test_a_sun_schedule_action_is_a_callback_job(hass, monkeypatch, mode, fn):
    """A plain function becomes an executor job (a worker thread), where async_create_task is refused."""
    c = await _zone(hass)
    seen = []
    monkeypatch.setattr(controller_module, fn, lambda hass_, action, offset=None: seen.append(action) or (lambda: None))
    called = []
    c._track_schedule(mode, 15, dt_time(5, 30), lambda now: called.append(now))
    assert seen and HassJob(seen[0]).job_type is HassJobType.Callback
    seen[0]()
    assert called == [None]


@pytest.mark.asyncio
async def test_the_stuck_valve_alert_and_abort_still_go_out_when_the_close_fails(hass):
    c = await _zone(hass)
    async def boom(call):
        raise HomeAssistantError("device offline")
    hass.services.async_register("switch", "turn_off", boom)
    events = []
    async def log_event(**kw):
        events.append(kw["event_type"])
    c._log_event = log_event
    await c.store.async_save()
    await c._fire_valve_stuck()
    assert "Valve Stuck Watchdog Fired" in events
    assert c.store.state.abort_on is True and c.store.state.lock_on is False


@pytest.mark.asyncio
async def test_copying_settings_that_reload_the_zone_is_refused_while_it_waters(hass):
    c = await _zone(hass)
    changed = {"options": {CONF_DEEP_SOAK_ENABLED: not bool(c.deep_soak_enabled)}, "numbers": {}, "state": {}}
    c.store.state.lock_on = True
    with pytest.raises(ServiceValidationError):
        await presets.async_apply(hass, c, changed)
    c.store.state.lock_on = False
    # nothing to reload (no option differs): fine even while busy
    c.store.state.lock_on = True
    await presets.async_apply(hass, c, {"options": {}, "numbers": {}, "state": {}})
    c.store.state.lock_on = False


@pytest.mark.asyncio
async def test_the_deep_soak_switch_is_refused_while_the_zone_waters(hass):
    from homeassistant.helpers import entity_registry as er

    c = await _zone(hass)
    reg = er.async_get(hass)
    ent = next(e.entity_id for e in reg.entities.values() if e.config_entry_id == c.entry.entry_id and e.entity_id.startswith("switch.") and e.entity_id.endswith("deep_soak_enabled"))
    before = c.deep_soak_enabled
    c.store.state.lock_on = True
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("switch", "turn_off" if before else "turn_on", {"entity_id": ent}, blocking=True)
    c.store.state.lock_on = False
    assert c.deep_soak_enabled == before


@pytest.mark.asyncio
async def test_a_repeated_rain_total_adds_no_sample_and_no_write(hass):
    c = await _zone(hass)
    c._record_rain_sample(seed_only=False)  # make sure there is a first sample
    n = len(c.store.state.rain_samples)
    saves = []
    c.store.schedule_save = lambda *a, **k: saves.append(1)
    c._record_rain_sample(seed_only=False)
    c._record_rain_sample(seed_only=False)
    assert len(c.store.state.rain_samples) == n and saves == []
    c.store.state.rain_counter_total_tips = (c.store.state.rain_counter_total_tips or 0.0) + 5
    c._record_rain_sample(seed_only=False)
    assert len(c.store.state.rain_samples) == n + 1 and saves == [1]


@pytest.mark.asyncio
async def test_an_offline_valve_is_not_confirmed_closed(hass):
    c = await _zone(hass)
    valve = c.valve_entity
    for state, expected in (("off", True), ("unavailable", False), ("unknown", False), ("on", False)):
        hass.states.async_set(valve, state)
        assert await c._valve_confirmed_closed(valve, seconds=0.5) is expected, state
    hass.states.async_remove(valve)
    assert await c._valve_confirmed_closed(valve, seconds=0.5) is True  # no such entity: nothing to hold


@pytest.mark.asyncio
async def test_frequent_saves_are_delayed_and_an_unload_still_writes_everything(hass, hass_storage):
    c = await _zone(hass)
    c.store.state.today_peak_temp_c = 41.5
    c.store.schedule_save()
    await c.async_unload() if hasattr(c, "async_unload") else await c.async_shutdown()
    saved = next(v for k, v in hass_storage.items() if k.startswith(f"{DOMAIN}_") and "plants" not in k and "presets" not in k)
    assert saved["data"]["today_peak_temp_c"] == 41.5


@pytest.mark.asyncio
async def test_a_restart_across_the_daily_shift_does_not_lose_the_day(hass):
    """HA was down at 23:59:50: the open bucket's day still lands in the histories at the next start."""
    import homeassistant.util.dt as dt_util
    from datetime import timedelta

    c = await _zone(hass)
    s = c.store.state
    today = dt_util.now().date()
    two_ago = today - timedelta(days=2)
    midnight_two_ago = dt_util.start_of_local_day(two_ago).timestamp()
    s.rain_samples = [[midnight_two_ago + 3600, 100.0], [midnight_two_ago + 20 * 3600, 112.0], [midnight_two_ago + 30 * 3600, 112.0], [dt_util.utcnow().timestamp() - 60, 112.0]]
    s.today_date_iso = two_ago.isoformat()
    s.today_peak_temp_c, s.today_min_temp_c = 33.0, 21.0
    s.last_shift_date_iso = None
    s.peak_temp_day_history_c, s.min_temp_day_history_c = [None, None, None], [None, None, None]
    s.rain_day_history_mm = [0.0] * 10
    c._start_new_day()
    # two whole days ended (two days ago, yesterday): newest first
    assert s.peak_temp_day_history_c[:2] == [None, 33.0] and s.min_temp_day_history_c[:2] == [None, 21.0]
    assert s.rain_day_history_mm[1] == pytest.approx(12.0) and s.rain_day_history_mm[0] == pytest.approx(0.0)
    assert s.today_date_iso == today.isoformat()


@pytest.mark.asyncio
async def test_a_day_the_shift_already_closed_is_not_shifted_twice(hass):
    import homeassistant.util.dt as dt_util
    from datetime import timedelta

    c = await _zone(hass)
    s = c.store.state
    yesterday = dt_util.now().date() - timedelta(days=1)
    s.today_date_iso = yesterday.isoformat()
    s.last_shift_date_iso = yesterday.isoformat()  # the 23:59:50 shift ran
    s.rain_day_history_mm = [7.0] + [0.0] * 9
    s.peak_temp_day_history_c = [30.0, None, None]
    c._start_new_day()
    assert s.rain_day_history_mm[0] == 7.0 and s.peak_temp_day_history_c[0] == 30.0
