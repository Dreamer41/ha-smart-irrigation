# Avocado Irrigation

A native Home Assistant custom integration that replicates the confirmed-final
`automations.yaml` avocado irrigation system (14-day pulsed deep soak + daily
smart precision routine irrigation, rain accumulation from a tipping-bucket
gauge, dry-down memory, and five safety watchdogs) as real Python code
instead of YAML automations.

This is a **from-scratch rewrite**, not a patch of the earlier feature
branch — that branch had drifted from the true final YAML (e.g. it describes
a manual-reset-only "fault lockout" and a "runtime - 1 minute" execution
quirk that don't exist in your actual `automations.yaml` — you'd deliberately
chosen auto-recovering watchdogs over a manual lockout months ago). It was
wiped and rebuilt directly against the live `automations.yaml` /
`configuration.yaml` read on 2026-09-14/15.

## What it does *not* change

It never creates or renames any of your physical entities. You point it, via
the config flow, at your existing:

- valve switch (`switch.watering1`)
- pump power sensor (`sensor.waterpump_power_power`)
- rain gauge tip counter (`counter.rain_gauge_tips`)
- outdoor temperature sensor (`sensor.outdoor_temp_temperature`)
- (optional) a `notify.*` entity for phone alerts

Everything else — the 8 rolling rain-window sensors, the 10-day rain history,
the 3-day peak-temp history, the mutex lock, the abort flag, the last-run
timestamps — is now internal state in this integration (persisted to its own
storage file), replacing the input_number/input_boolean/input_datetime
helpers the YAML version used for the same bookkeeping.

## Parity notes — read before trusting this with the real valve

- **18 tunable numbers**, 1:1 with your input_number sliders (same name,
  min/max/step/unit, same fallback default as the Jinja `| float(x)` in the
  YAML). See `const.py` `NUMBER_DEFS` / `NUMBER_DEFAULTS`.
- **Manual buttons/services call the exact same code as the scheduled
  triggers** — `run_deep_soak` / `run_routine_irrigation` don't know or care
  whether they were invoked by the clock or by you, so a manual run can never
  drift from what the 05:00/05:30 schedule would have done. Both still
  respect every rain/dry-down/mutex gate, same as the live YAML.
- **Two disclosed, deliberate deviations from the YAML** (flagged per your
  "never silently change behavior" rule, not silently folded in):
  1. The YAML had two near-duplicate "clear a stuck lock on HA restart"
     automations. This port merges them into one `_on_startup` handler doing
     everything the richer of the two did (see `controller.py` module
     docstring).
  2. The rolling rain windows (past 15/30/60min, 24h, 3d, 4d, 7d, 14d) are
     computed from a persisted list of `(timestamp, cumulative_mm)` samples
     rather than 8 separate recorder-backed `statistics` sensors. For a
     monotonically increasing source (which `rain_lifetime_mm` always is)
     these are mathematically equivalent; see `rain_tracker.py`'s docstring
     and `tests/test_rain_tracker.py`.
- **Not yet independently verified against a live HA instance** — I don't
  have a Home Assistant install to run this against in the sandbox I built
  it in (a full `pip install homeassistant` failed on an unrelated native
  dependency, PyRIC). What *is* verified:
  - All modules import-clean and pass `pyflakes` with zero warnings.
  - The pure calculation logic (`calculations.py`, `rain_tracker.py`) has 18
    unit tests (`tests/`) that pass, checked against hand-computed values
    from the actual Jinja expressions, not just self-consistency.
  - I read every line of the relevant `automations.yaml` and
    `configuration.yaml` sections directly from your live config and cross-
    checked each condition/threshold/formula against this code by hand.
  - What I could **not** test here: the actual Home Assistant entity
    lifecycle (config flow, `RestoreNumber` restore behavior, service
    registration, the exact event-loop timing of `async_track_point_in_time`
    watchdogs). That only shows up once it's running on your HA. Treat the
    cutover plan below as mandatory, not optional, precisely because of this
    gap.

## Installation

1. Copy `custom_components/avocado_irrigation/` into your HA `/config/custom_components/`
   (already done for you at `Y:\custom_components\avocado_irrigation` if you're
   reading this from that copy).
2. Restart Home Assistant (custom integrations need a full restart to be
   picked up the first time).
3. Settings → Devices & Services → Add Integration → "Avocado Irrigation".
4. Point it at your real entities. For the CSV path, use a **different file**
   than your existing `/config/avocado_irrigation.csv` during testing (the
   default is `/config/avocado_irrigation_v2.csv`) so you can diff the two
   logs side by side.

## Recommended cutover (do not skip — this controls a live valve on your
## shared house water pump)

1. **Install alongside the YAML automations, don't disable them yet.** Leave
   `avocado_deep_soak` / `avocado_routine_irrigation` enabled so your tree
   keeps getting watered on the schedule you trust while you test this.
2. **Bench-test the wiring first**, at a time when it's fine for the valve to
   click on for a few seconds:
   `Developer Tools → Actions → avocado_irrigation.test_pulse` (seconds: 10).
   This bypasses every schedule/rain/dry-down gate on purpose — it's the one
   place in this integration that does — so you can confirm the valve
   switches, the pump-power sensor is read correctly, and a CSV row lands in
   `avocado_irrigation_v2.csv`.
3. **Compare a full day of diagnostics against the YAML's own sensors**
   before it ever controls the valve on schedule:
   - `sensor.avocado_irrigation_rain_past_24h/3d/7d/14d` vs your existing
     `sensor.rain_past_24h/3d/7d/14d`
   - `sensor.avocado_irrigation_3_day_average_peak_temperature` vs
     `sensor.3_day_average_peak_temperature`
   - `sensor.avocado_irrigation_next_irrigation_estimate` vs
     `sensor.next_avocado_irrigation`
   These should track each other closely (small rounding differences are
   expected; a large or growing gap means something's off and is worth
   sending back for another look before going further).
4. **Only once those match for a few days**, disable the two YAML
   automations (`avocado_deep_soak`, `avocado_routine_irrigation`) — leave
   the five YAML watchdogs disabled too, since this integration has its own
   equivalents — and let this integration run the actual 05:00/05:30 cycles.
5. **Rollback plan**: if anything looks wrong after cutover, re-enable the
   two YAML automations and disable this integration's config entry
   (Settings → Devices & Services → Avocado Irrigation → ⋮ → Disable). The
   YAML automations and this integration read the same physical valve/pump/
   rain-gauge entities but keep entirely separate internal state, so neither
   can corrupt the other's bookkeeping.

## Services

- `avocado_irrigation.run_deep_soak` / `run_routine_irrigation` — same gates
  as the schedule.
- `avocado_irrigation.reset_lock` — emergency mutex clear.
- `avocado_irrigation.test_pulse` (seconds, default 10) — bench-test only,
  bypasses all gates.
