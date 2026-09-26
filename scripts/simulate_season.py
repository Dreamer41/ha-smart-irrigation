#!/usr/bin/env python3
"""Fast, offline "what would the irrigation do over N days" simulator.

This does NOT boot Home Assistant, asyncio, or any of the test harness --
it drives the same pure math in `custom_components/zoneflow/
calculations.py` directly, day by day, with synthetic weather. That's what
makes it fast (a 60-day run finishes in well under a second) and immune to
all the pytest/Windows/event-loop trouble the automated test suite has to
deal with -- it's plain Python, no dependencies beyond the stdlib (matplotlib
is optional, only needed for --chart).

Use this to sanity-check the *planning* behaviour over a season -- does it
water enough in a dry spell, does it back off correctly through a monsoon
burst, roughly how much total water gets used -- before waiting on the real
tree for two months to find out. It intentionally does NOT model the
30-minute pre-irrigation rain cancellation gate, the mutex lock's minute-by-
minute timing, or the safety watchdogs (valve stuck, power loss) -- those are
already covered by the millisecond-accurate pytest suite in tests/. This
script is for the day-to-day watering *decisions* over a long stretch, not
the safety machinery.

Examples
--------
    python scripts/simulate_season.py
    python scripts/simulate_season.py --days 60 --scenario monsoon
    python scripts/simulate_season.py --scenario dry --seed 7 --csv out.csv
    python scripts/simulate_season.py --scenario mixed --chart season.png
"""
from __future__ import annotations

import argparse
import csv as csv_module
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.zoneflow import calculations as calc  # noqa: E402
from custom_components.zoneflow.const import (  # noqa: E402
    GROWTH_RAMP_CURVES,
    GROWTH_RAMP_OFF,
    GROWTH_RAMP_PROFILE_OPTIONS,
    NUMBER_DEFAULTS,
)

DAY_SECONDS = 86400

# Fixed structural constants (mirrors const.py -- see that file for why these
# aren't sliders).
DEEP_SOAK_INTERVAL_DAYS = 14
DEEP_SOAK_INTERVAL_BUFFER_SECONDS = 6 * 3600
ROUTINE_INTERVAL_BUFFER_SECONDS = 6 * 3600
SIGNIFICANT_RAIN_24H_MM = 35.0
SIGNIFICANT_RAIN_4D_MM = 50.0
SIGNIFICANT_RAIN_7D_MM = 100.0


# ---------------------------------------------------------------------------
# Weather scenarios. Each returns (rain_mm, peak_temp_c) for day index `d`.
# Tuned loosely for a tropical (Koh Samui-like) climate: hot most of the
# year, rain arriving in bursts rather than evenly, not a single "average"
# drizzly day. Adjust freely -- these are illustrative starting points, not
# calibrated to any specific forecast.
# ---------------------------------------------------------------------------
def scenario_dry(d: int, rng: random.Random) -> tuple[float, float]:
    """Long dry stretch: rain is rare and light, temps run hot."""
    temp = 32.0 + rng.uniform(-1.5, 2.5)
    rain = 0.0
    if rng.random() < 0.08:  # occasional light shower
        rain = rng.uniform(1, 8)
    return rain, temp


def scenario_monsoon(d: int, rng: random.Random) -> tuple[float, float]:
    """Frequent rain, some heavy bursts, slightly cooler."""
    temp = 29.0 + rng.uniform(-2.0, 1.5)
    roll = rng.random()
    if roll < 0.10:
        rain = rng.uniform(30, 70)  # heavy burst
    elif roll < 0.45:
        rain = rng.uniform(2, 20)  # ordinary rain day
    else:
        rain = 0.0
    return rain, temp


def scenario_mixed(d: int, rng: random.Random) -> tuple[float, float]:
    """A transition season: starts drier and hotter, drifts rainier and
    slightly cooler over the run -- e.g. hot season sliding into monsoon."""
    progress = d / 60.0  # 0 -> 1 over ~2 months, gently extrapolates past that
    temp = (33.0 - 3.0 * progress) + rng.uniform(-1.5, 1.5)
    roll = rng.random()
    rain_chance = 0.08 + 0.30 * progress
    heavy_chance = 0.01 + 0.07 * progress
    if roll < heavy_chance:
        rain = rng.uniform(25, 60)
    elif roll < rain_chance:
        rain = rng.uniform(1, 15)
    else:
        rain = 0.0
    return rain, temp


def scenario_random(d: int, rng: random.Random) -> tuple[float, float]:
    """No seasonal shape at all -- pure noise, for stress-testing edge cases
    (long dry runs, rain-on-rain, temp swings) rather than realism."""
    temp = rng.uniform(22.0, 38.0)
    roll = rng.random()
    if roll < 0.05:
        rain = rng.uniform(30, 90)
    elif roll < 0.30:
        rain = rng.uniform(0.5, 25)
    else:
        rain = 0.0
    return rain, temp


SCENARIOS = {
    "dry": scenario_dry,
    "monsoon": scenario_monsoon,
    "mixed": scenario_mixed,
    "random": scenario_random,
}


@dataclass
class DayResult:
    day_index: int
    calendar_date: date
    rain_mm: float
    peak_temp_c: float
    avg_peak_temp_c: float | None
    action: str
    applied_mm: float
    growth_ramp_pct: float = 100.0
    note: str = ""


@dataclass
class SimState:
    last_deep_soak_day: float = float("-inf")
    last_routine_day: float = float("-inf")
    last_significant_rain_day: float = float("-inf")
    rain_history_mm: list[float] = field(default_factory=lambda: [0.0] * 10)
    temp_history_c: list[float | None] = field(default_factory=lambda: [None, None, None])
    rain_threshold_flags: dict[str, bool] = field(default_factory=lambda: {"24h": False, "4d": False, "7d": False})
    daily_rain_log: list[float] = field(default_factory=list)  # for rolling-window sums


def rolling_sum(daily_rain_log: list[float], window_days: int) -> float:
    return sum(daily_rain_log[-window_days:]) if daily_rain_log else 0.0


def run_simulation(
    days: int,
    scenario: str,
    seed: int,
    numbers: dict[str, float],
    growth_ramp_profile: str = GROWTH_RAMP_OFF,
    planting_day: int = 0,
) -> list[DayResult]:
    rng = random.Random(seed)
    gen = SCENARIOS[scenario]
    state = SimState()
    results: list[DayResult] = []
    ramp_curve = GROWTH_RAMP_CURVES.get(growth_ramp_profile)

    for d in range(days):
        rain_mm, peak_temp = gen(d, rng)

        # Growth-stage auto-ramp (see const.py's GROWTH_RAMP_CURVES / the
        # "revamp" notes): only ever scales the ROUTINE weekly targets, the
        # same restriction controller.py's growth_ramp_fraction() applies --
        # deep soak's target depth models root-zone penetration, which
        # doesn't shrink for a young plant the way day-to-day routine
        # watering does. "off" (the default) always yields 100%, matching
        # a zone that never touches this feature getting identical results
        # to before it existed.
        if growth_ramp_profile == GROWTH_RAMP_OFF or ramp_curve is None:
            growth_ramp = 1.0
        else:
            growth_ramp = calc.growth_ramp_fraction(d - planting_day, ramp_curve)

        # -- Decisions use *yesterday-and-earlier* history, mirroring the
        # real automation's 05:00/05:30 checks running before today's rain
        # has accumulated. --
        # No real day on record (the first days): None, which the tier
        # functions treat as the normal tier (the integration would use the
        # zone's fallback temperature, which sits in the normal band by
        # default).
        avg_peak_temp = calc.three_day_average_peak_temp(state.temp_history_c)
        action = "none"
        applied_mm = 0.0
        note = ""

        # --- Deep soak check (runs first, like the 05:00 trigger) ---
        deep_soak_elapsed_days = d - state.last_deep_soak_day
        deep_soak_ran = False
        if calc.deep_soak_due(
            deep_soak_elapsed_days * DAY_SECONDS, DEEP_SOAK_INTERVAL_DAYS, DEEP_SOAK_INTERVAL_BUFFER_SECONDS
        ):
            rain_drydown_elapsed = (d - state.last_significant_rain_day) * DAY_SECONDS
            if calc.drydown_satisfied(rain_drydown_elapsed, numbers["deep_soak_drydown_days"]):
                rain_14d = rolling_sum(state.daily_rain_log, 14)
                if rain_14d < numbers["deep_soak_rain_threshold"]:
                    plan = calc.plan_deep_soak(numbers["deep_soak_target_mm"], numbers["flow_rate_mm_per_min"])
                    if plan.total_runtime_minutes > numbers["deep_soak_max_runtime_minutes"]:
                        action, note = "deep_soak_cap_exceeded", f"runtime {plan.total_runtime_minutes}min > cap"
                    else:
                        action = "deep_soak"
                        applied_mm = plan.target_mm
                        state.last_deep_soak_day = d
                        deep_soak_ran = True
                        note = f"{plan.total_runtime_minutes}min runtime"
                else:
                    note = f"deep soak skipped: 14d rain {rain_14d:.1f}mm >= threshold"
            else:
                note = "deep soak skipped: subsoil still wet"

        # --- Routine check (05:30 trigger). Real system: if deep soak just
        # ran, the mutex lock is still held past 05:30, so routine is
        # skipped for today -- modeled here the same way. ---
        if not deep_soak_ran:
            hot_threshold = numbers["hot_temp_threshold"]
            interval_days = calc.routine_interval_days(avg_peak_temp, hot_threshold)
            routine_elapsed_days = d - state.last_routine_day
            if calc.routine_due(routine_elapsed_days * DAY_SECONDS, interval_days, ROUTINE_INTERVAL_BUFFER_SECONDS):
                rain_drydown_elapsed = (d - state.last_significant_rain_day) * DAY_SECONDS
                if calc.drydown_satisfied(rain_drydown_elapsed, numbers["routine_drydown_days"]):
                    days_elapsed_int = 999 if routine_elapsed_days == float("inf") else int(routine_elapsed_days)
                    plan = calc.plan_routine_irrigation(
                        avg_peak_temp=avg_peak_temp,
                        hot_threshold=hot_threshold,
                        cool_threshold=numbers["cool_temp_threshold"],
                        normal_weekly_mm=numbers["target_weekly_mm"] * growth_ramp,
                        hot_weekly_mm=numbers["target_weekly_hot_mm"] * growth_ramp,
                        cool_weekly_mm=numbers["target_weekly_cool_mm"] * growth_ramp,
                        flow_rate=numbers["flow_rate_mm_per_min"],
                        days_elapsed=days_elapsed_int,
                        today_rain_mm=0.0,  # decision happens before today's rain accrues
                        rain_day_history_mm=state.rain_history_mm,
                        rain_eff_low=numbers["rain_eff_low"],
                        rain_eff_mid=numbers["rain_eff_mid"],
                        rain_eff_high=numbers["rain_eff_high"],
                    )
                    if plan.calc_runtime_minutes > numbers["max_runtime_minutes"]:
                        action = "routine_cap_exceeded"
                        note = f"runtime {plan.calc_runtime_minutes}min > cap"
                    elif plan.calc_runtime_minutes <= 0:
                        action = "routine_rained_out"
                        note = f"rain deduction ({plan.eff_rain_mm:.1f}mm) covered full target"
                    else:
                        action = "routine"
                        applied_mm = plan.needed_mm
                        state.last_routine_day = d
                        note = f"{plan.calc_runtime_minutes}min runtime, {plan.eff_rain_mm:.1f}mm rain-deducted"
                else:
                    note = "routine skipped: rain dry-down not satisfied"

        results.append(
            DayResult(
                day_index=d,
                calendar_date=date.today() + timedelta(days=d),
                rain_mm=round(rain_mm, 1),
                peak_temp_c=round(peak_temp, 1),
                avg_peak_temp_c=round(avg_peak_temp, 1) if avg_peak_temp is not None else None,
                action=action,
                applied_mm=round(applied_mm, 1),
                growth_ramp_pct=round(growth_ramp * 100, 0),
                note=note,
            )
        )

        # --- End-of-day bookkeeping: significant-rain edge detection, then
        # shift the rolling history registers (mirrors the 23:59:50 shift). ---
        state.daily_rain_log.append(rain_mm)
        checks = {
            "24h": (rain_mm, SIGNIFICANT_RAIN_24H_MM),
            "4d": (rolling_sum(state.daily_rain_log, 4), SIGNIFICANT_RAIN_4D_MM),
            "7d": (rolling_sum(state.daily_rain_log, 7), SIGNIFICANT_RAIN_7D_MM),
        }
        fired = False
        for key, (value, threshold) in checks.items():
            was_above = state.rain_threshold_flags[key]
            is_above = value > threshold
            state.rain_threshold_flags[key] = is_above
            if is_above and not was_above:
                fired = True
        if fired:
            state.last_significant_rain_day = d

        state.rain_history_mm = [round(rain_mm, 2), *state.rain_history_mm[:9]]
        state.temp_history_c = [round(peak_temp, 2), state.temp_history_c[0], state.temp_history_c[1]]

    return results


def print_report(results: list[DayResult], show_ramp: bool = False) -> None:
    ramp_col = f" {'Ramp':>5} " if show_ramp else " "
    header = f"{'Date':<11} {'Rain':>6} {'Peak':>6} {'3dAvg':>6} {ramp_col} {'Action':<20} {'Applied':>8}  Note"
    print(header)
    print("-" * len(header))
    for r in results:
        marker = ""
        if r.action == "deep_soak":
            marker = "  <-- DEEP SOAK"
        elif r.action == "routine":
            marker = "  <-- routine"
        ramp_field = f"{r.growth_ramp_pct:>4.0f}% " if show_ramp else ""
        print(
            f"{r.calendar_date.isoformat():<11} {r.rain_mm:>5.1f}m {r.peak_temp_c:>5.1f}C "
            f"{r.avg_peak_temp_c if r.avg_peak_temp_c is not None else float('nan'):>5.1f}C  {ramp_field}{r.action:<20} {r.applied_mm:>6.1f}mm  {r.note}{marker}"
        )

    total_days = len(results)
    total_rain = sum(r.rain_mm for r in results)
    deep_soaks = [r for r in results if r.action == "deep_soak"]
    routines = [r for r in results if r.action == "routine"]
    total_applied = sum(r.applied_mm for r in results)
    capped = [r for r in results if "cap_exceeded" in r.action]
    rained_out = [r for r in results if r.action == "routine_rained_out"]

    watered_days = sorted(r.day_index for r in results if r.action in ("deep_soak", "routine"))
    longest_gap = 0
    if watered_days:
        prev = -1
        for day in watered_days:
            longest_gap = max(longest_gap, day - prev)
            prev = day
        longest_gap = max(longest_gap, total_days - 1 - prev)
    else:
        longest_gap = total_days

    print()
    print("=" * len(header))
    print(f"Summary over {total_days} simulated days")
    print(f"  Total natural rainfall:     {total_rain:6.1f} mm")
    print(f"  Deep soak cycles:           {len(deep_soaks):3d}  ({sum(r.applied_mm for r in deep_soaks):.1f}mm applied)")
    print(f"  Routine irrigation cycles:  {len(routines):3d}  ({sum(r.applied_mm for r in routines):.1f}mm applied)")
    print(f"  Routine cycles fully rained out: {len(rained_out)}")
    print(f"  Safety-cap aborts:          {len(capped)}")
    print(f"  Total irrigation applied:   {total_applied:6.1f} mm")
    print(f"  Longest stretch w/o any irrigation: {longest_gap} days")


def write_csv(results: list[DayResult], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv_module.writer(handle)
        writer.writerow(
            ["date", "rain_mm", "peak_temp_c", "avg_peak_temp_c", "growth_ramp_pct", "action", "applied_mm", "note"]
        )
        for r in results:
            writer.writerow(
                [
                    r.calendar_date.isoformat(),
                    r.rain_mm,
                    r.peak_temp_c,
                    r.avg_peak_temp_c,
                    r.growth_ramp_pct,
                    r.action,
                    r.applied_mm,
                    r.note,
                ]
            )


def write_chart(results: list[DayResult], path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed -- skipping --chart (pip install matplotlib)", file=sys.stderr)
        return

    dates = [r.calendar_date for r in results]
    rain = [r.rain_mm for r in results]
    temp = [r.peak_temp_c for r in results]
    applied = [r.applied_mm for r in results]
    deep_soak_x = [r.calendar_date for r in results if r.action == "deep_soak"]
    routine_x = [r.calendar_date for r in results if r.action == "routine"]

    fig, (ax1, ax3) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, height_ratios=[2, 1])

    ax1.bar(dates, rain, color="#4a90d9", width=0.9, label="Rain (mm)")
    ax1.set_ylabel("Rain (mm)", color="#4a90d9")
    ax2 = ax1.twinx()
    ax2.plot(dates, temp, color="#d94a4a", linewidth=1.5, label="Peak temp (C)")
    ax2.set_ylabel("Peak temp (C)", color="#d94a4a")
    for x in deep_soak_x:
        ax1.axvline(x, color="#2e8b57", linestyle="--", alpha=0.7)
    for x in routine_x:
        ax1.axvline(x, color="#c9a227", linestyle=":", alpha=0.6)
    ax1.set_title("Weather + irrigation events (green dashed = deep soak, yellow dotted = routine)")

    ax3.bar(dates, applied, color="#2e8b57", width=0.9)
    ax3.set_ylabel("Applied (mm)")
    ax3.set_xlabel("Date")

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"Chart written to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=60, help="number of days to simulate (default 60, ~2 months)")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="mixed", help="weather pattern (default mixed)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed, for reproducible runs (default 42)")
    parser.add_argument("--csv", type=Path, default=None, help="also write the day-by-day table to this CSV path")
    parser.add_argument("--chart", type=Path, default=None, help="also write a PNG chart (requires matplotlib)")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="key=value",
        help="override one of the tunable numbers (see const.py NUMBER_DEFAULTS), e.g. --set target_weekly_mm=45",
    )
    parser.add_argument(
        "--growth-ramp",
        choices=sorted(GROWTH_RAMP_PROFILE_OPTIONS),
        default=GROWTH_RAMP_OFF,
        help="optional growth-stage auto-ramp profile (default off -- always 100%%, matches pre-revamp behavior)",
    )
    parser.add_argument(
        "--planting-day",
        type=int,
        default=0,
        help="simulated day index the crop was planted/transplanted (default 0, i.e. the run starts at planting)",
    )
    args = parser.parse_args()

    numbers = dict(NUMBER_DEFAULTS)
    for item in args.set:
        key, _, value = item.partition("=")
        if key not in numbers:
            parser.error(f"unknown tunable number {key!r} (see const.py NUMBER_DEFAULTS)")
        numbers[key] = float(value)

    results = run_simulation(
        args.days, args.scenario, args.seed, numbers, growth_ramp_profile=args.growth_ramp, planting_day=args.planting_day
    )
    print_report(results, show_ramp=args.growth_ramp != GROWTH_RAMP_OFF)

    if args.csv:
        write_csv(results, args.csv)
        print(f"\nCSV written to {args.csv}")
    if args.chart:
        write_chart(results, args.chart)


if __name__ == "__main__":
    main()
