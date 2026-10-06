"""Changing the rain gauge's mm per tip must never make rain: the stored
samples hold cumulative mm (tips x mm per tip), so a calibration that
differs from the one they were recorded with used to show up as a jump of
(all tips so far) x (the difference) on the next tip -- about 4 mm at 436
tips and 0.009 mm more per tip. A restart that read the default before the
saved calibration was restored did the same."""
import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_manual_rain import _setup
from .test_smoke_setup import RAIN_COUNTER


async def _zone(hass, tmp_path):
    entry, controller = await _setup(hass, csv_path=str(tmp_path / "f.csv"))
    # A gauge that already has a long history: 436 tips counted so far.
    state = controller.store.state
    state.rain_counter_total_tips = state.rain_counter_last_tips = 436.0
    state.rain_samples = []
    state.rain_samples_mm_per_tip = None
    hass.states.async_set(RAIN_COUNTER, "436")
    await hass.async_block_till_done()
    return entry, controller


async def _tip(hass, value):
    hass.states.async_set(RAIN_COUNTER, str(value))
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_a_calibration_change_makes_no_phantom_rain(hass, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    await controller.numbers["rain_mm_per_tip"].async_set_metric_value(0.3)
    await _tip(hass, 437)
    base = controller.rain_windows()["24h"]
    # The calibration is corrected, then the next real tip arrives.
    await controller.numbers["rain_mm_per_tip"].async_set_metric_value(0.309)
    await _tip(hass, 438)
    after = controller.rain_windows()["24h"]
    # Two real tips since the first, at the corrected size: 0.309 each, not
    # 436 x 0.009 = 3.9 mm on top.
    assert after == pytest.approx(2 * 0.309, abs=0.01)
    assert after - base < 0.5


@pytest.mark.asyncio
async def test_a_default_read_at_startup_then_the_saved_value_makes_no_phantom_rain(hass, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    await controller.numbers["rain_mm_per_tip"].async_set_metric_value(0.309)
    await _tip(hass, 437)
    await _tip(hass, 438)
    # The state as a restart can leave it: samples recorded with another
    # calibration than the one in use.
    controller.store.state.rain_samples_mm_per_tip = 0.2997
    tracker = controller.store.state.rain_tracker()
    tracker.samples = [(ts, mm / 0.309 * 0.2997) for ts, mm in tracker.samples]
    controller.store.state.save_rain_tracker(tracker)
    await _tip(hass, 439)
    assert controller.rain_windows()["24h"] == pytest.approx(0.309 * 3, abs=0.01)


@pytest.mark.asyncio
async def test_rain_today_starts_at_zero_on_a_gauge_that_already_has_a_count(hass, tmp_path):
    """A zone set up on (or switched to) a sensor that already holds 436 tips
    must not call that history rain of today."""
    from .test_manual_rain import _setup

    hass.states.async_set(RAIN_COUNTER, "436")
    entry, controller = await _setup(hass, csv_path=str(tmp_path / "f.csv"))
    # _setup writes 0 first; start the way a fresh zone does: no samples yet.
    state = controller.store.state
    state.rain_samples = []
    state.rain_counter_total_tips = state.rain_counter_last_tips = None
    state.rain_midnight_baseline_mm = 0.0
    hass.states.async_set(RAIN_COUNTER, "436")
    controller._sync_rain_from_counter_state(hass.states.get(RAIN_COUNTER), seed_only=True)
    assert controller.today_rain_mm() == 0.0
    await _tip(hass, 437)
    assert controller.today_rain_mm() == pytest.approx(0.2997, abs=0.01)


@pytest.mark.asyncio
async def test_no_setting_change_makes_phantom_rain_or_changes_the_history(hass, tmp_path):
    """Move every numeric setting to its minimum and its maximum, with a tip
    after each: the rain only ever grows by that tip, and the rain already
    recorded does not change (except by the tip size itself, which rescales
    the whole record, as a corrected calibration should)."""
    from custom_components.zoneflow.const import NUMBER_DEFS

    entry, controller = await _zone(hass, tmp_path)
    tips = 436
    await _tip(hass, tips + 1)
    tips += 1
    mm_per_tip = controller.number("rain_mm_per_tip")
    expected_total = mm_per_tip  # one real tip so far
    assert controller.rain_windows()["24h"] == pytest.approx(expected_total, abs=0.01)
    failures = []
    exercised = 0
    for key, (_name, low, high, _step, _unit) in NUMBER_DEFS.items():
        entity = controller.numbers.get(key)
        if entity is None:
            continue
        exercised += 1
        for value in (high, low):
            before_ratio = 1.0
            if key == "rain_mm_per_tip":
                before_ratio = value / controller.number("rain_mm_per_tip")
            await entity.async_set_metric_value(value)
            expected_total *= before_ratio
            await _tip(hass, tips + 1)
            tips += 1
            expected_total += controller.number("rain_mm_per_tip")
            got = controller.rain_windows()["24h"]
            if abs(got - expected_total) > 0.02:
                failures.append((key, value, round(got, 3), round(expected_total, 3)))
                expected_total = got  # carry on from what it shows
    assert exercised > 30
    assert not failures, failures
