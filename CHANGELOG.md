# ZoneFlow Changelog

All notable changes to this project are documented here.

For detailed release notes and upgrade instructions, see the **docs/** folder for each version.

## [1.6.0] — Greenhouse & indoor climate control

- **New**: zone types — **outdoor** (as before), **greenhouse** and **indoor**. Existing zones stay outdoor; nothing changes for them. Change the type any time under Configure → Zone type, nothing is deleted
- **New**: climate control for greenhouse and indoor zones — **fans, vents (covers or switches), misters and a heater**, any number of each, from `switch`, `input_boolean`, `fan`, `cover`, `valve` and `climate` entities, driven by an inside temperature sensor and optional humidity, light and outside temperature sensors
- **New**: the valve is optional — a **climate-only zone** has no watering at all, and its watering settings, sensors, buttons and Repairs issues are hidden
- **New**: outside-air check — vents and fans only open when the outside air is cooler than inside, so a hot afternoon never gets hotter air
- **New**: misting by temperature, humidity or light, in short pulses with hard limits: confirmed off, one retry, then it halts until Reset Irrigation Lock, stuck-mister watchdog, Max Misting Per Hour, no misting at night / when cold / while heating / in frost
- **New**: failsafes — if the inside sensor fails (unavailable, or silent for **Sensor Offline After**, 4 hours by default), misters go off, vents and fans follow **Sensor Failsafe**, and the heater follows **Heater Failsafe** (off, part of the time, or part of the time while cold outside; 10 minutes on in every 20). While that heater may run in the cold, the vents stay shut
- **New**: every device command has a time limit, so a device that never answers can't stall the climate control
- **New**: **backup inside temperature sensors** — control carries on with the first working one, and you are told if main and backup disagree by more than 5 °C for 30 minutes
- **New**: Manual Hold — a device you switch yourself (in Home Assistant, with a wall button or the device's own app) or another automation switches is left alone for a set time; a device coming back from unavailable is not mistaken for you
- **New**: changing **Vent Open Position** moves vents that are already open; an outdoor zone changed to a greenhouse starts from its climate's temperatures
- **New**: turning **Greenhouse Control** off switches off a heater ZoneFlow had switched on
- **New**: Greenhouse Status, Inside VPD, Misting Today and Ventilation Allowed sensors, the Greenhouse Control switch, and about 20 climate settings that appear only when the hardware they act on is set up
- **New**: add or change sensors, backup sensors and devices later under Configure → Valve, sensors and climate devices — no re-setup
- **New**: the ZoneFlow card and overview card show climate zones (status, climate settings groups, greenhouse icon for valveless zones)
- **New**: all the new texts translated into the 19 languages (machine translated; corrections from native speakers welcome)
- **Docs**: new [Greenhouse and indoor zones guide](docs/GREENHOUSE.md); [AI_SETUP.md](AI_SETUP.md) gets a greenhouse and indoor section (§7.11) and updated questions and flow; README updated. If you have a heater, the guide recommends a hardware frost thermostat and a backup temperature sensor placed away from the main one
- **Fixed**: a climate-only zone no longer gets the irrigation "flow rate is still the default" Repairs warning
- **Tests**: full suite passes — 650 tests; climate engine also exercised on a sandbox Home Assistant (hot, outside-air check, cold, sensor loss and recovery, misting)

---

## [1.5.1] — Mulch Adjustment, Mark Watered & card fixes

- **New**: Mark Watered button — record a manual watering (hose, can); the routine clock restarts and the next run doesn't water again
- **New**: Zone card buttons (Water now, Deep soak now, Snooze, Fertilized, Service runs) act on one tap, with no "more info" popup to press again
- **New**: Hover tips on key settings in the card (English; more languages to follow)
- **Changed**: Finnish card wording for Water now / Deep soak now / Snooze / Fertilized

- **New**: Mulch adjustment for routine irrigation (select + slider) — account for bare-soil evaporation without hand-tuning Kc
- **New**: Mulch ET Adjustment slider (-50% to +70%, default 20%): up for exposed soil, down for water-holding soil such as heavy clay or shade
- **Fixed**: Home Assistant 2025.1+ background task compatibility (time-change listener race condition in test)
- **Docs**: New [Mulch feature guide](docs/MULCH.md), updated [AI_SETUP.md](AI_SETUP.md) climate adjustment section
- **Tests**: Full suite passes on HA 2024.3.3 (Py 3.11) and HA 2025.1.4 (Py 3.12) — 535 tests, zero regressions

See [docs/1.5.1-BETA.md](docs/1.5.1-BETA.md) for full details and upgrade instructions.

---

## [1.5.0] — Easier to Use

**Released**: 2026-09-14

- **Built-in ZoneFlow dashboard card** — add per zone, it finds entities automatically, shows only what the zone uses
- **ZoneFlow overview card** — every zone in one table: status, next/last watering, sorted by name or next watering
- **Status sensor** — one sentence per zone (watering now, what it decided today, or when it waters next)
- **Device page redesign** — Configuration & Diagnostic sections, cleaner layout, Download diagnostics button
- **Pause switch** & **Paused Until** date — stop watering temporarily
- **Frost guard** — hourly re-checks, uses temperature sensor or weather entity
- **Notifications** — per zone (all/warnings/none), weekly summary per phone
- **Repairs** — auto-detect: valve unavailable, sensor offline, missing notify target, uncalibrated flow
- **Plant presets** at setup, **flow-rate helper** from emitters or flow-meter measurement
- **Languages**: German, Dutch, French, Spanish, Italian, Finnish, Swedish, Polish, Portuguese (regional variants + Czech, Danish, Hungarian, Norwegian, Russian, Slovak, Ukrainian, Simplified Chinese)

---

## [1.4.3] — Service Mode & Deep Soak Integration

**Released**: 2026-08-20

- **Service Run buttons** — 1/5/10 min test watering
- **Service Mode switch** — keep valve open until switched off, auto-shutoff after 30 min with phone alert
- **Deep soak integration** — a completed deep soak counts as the routine watering; routine interval restarts from it

---

## [1.4.2] — Rain Efficiency & Deficit Mode

**Released**: 2026-07-15

- **Rain Efficiency** — what % of rainfall actually reaches the roots (depends on soil, drainage, slope)
- **Deficit Mode** — reduce watering during dry spells to encourage deep rooting
- **Split-cycle pulses** — for clay soils and slow drainage

---

## [1.4.1] — Deep Soak

**Released**: 2026-06-10

- **Deep soak cycle** — periodic deeper watering (1–2 weeks) to wet the full root zone
- **Configurable soak interval and target depth**
- **Hourly rechecks** — don't soak if rain recently fell

---

## [1.4.0] — Demand Models

**Released**: 2026-05-01

- **Interval-based demand model** — "water every N days" (simple, predictable)
- **ET curve demand model** — "water when ET₀ reaches X mm/day" (responds to weather, more efficient)
- **Switch between models** without losing configuration

---

## [1.3.0] — Scheduling & Forecast

**Released**: 2026-03-15

- **Routine irrigation schedule** — configurable time of day
- **Deep soak schedule** — separate time, independent of routine
- **Weather forecast gate** — skip watering if rain is forecast
- **Rain counter** — integrated rain measurement

---

## [1.2.0] — Soil & Site Configuration

**Released**: 2026-02-01

- **Soil type** — sandy, loam, clay (informational; drives recommended split-cycle, rain efficiency)
- **Drainage** — fast, medium, slow (informs deep-soak interval)
- **Slope** — flat, slight, moderate, steep (affects water runoff, infiltration)
- **Irrigation method** — drip, micro-sprinkler, sprinkler, soaker, other (determines emitter efficiency defaults)

---

## [1.1.0] — Foundation & Growth Ramp

**Released**: 2026-01-10

- **Growth ramp** — automatically scale back watering for young plants, ramp up as canopy fills
- **Crop coefficient (Kc)** — per-plant ET₀ adjustment
- **Hot/Cool/Normal temperature tiers** — respond to ambient heat
- **Pump safety** — cumulative runtime cap per day to prevent pump stress

---

## [1.0.0] — Initial Release

**Released**: 2025-12-15

- **ET₀-based irrigation scheduling** — Hargreaves-Samani reference evapotranspiration
- **Zone-by-zone scheduling** — independent for each valve
- **Flow rate & valve control** — pulse-count or timed cycles
- **Home Assistant integration** — entities for every parameter, automatable via services
- **CSV logging** — water used, rain, ET₀, decisions (for analysis & debugging)

---

## Versioning

ZoneFlow follows [Semantic Versioning](https://semver.org/):
- **MAJOR** (X.0.0): Breaking changes to dashboard/configuration or major new features
- **MINOR** (X.Y.0): New features, non-breaking changes
- **PATCH** (X.Y.Z): Bug fixes, documentation, translations

---

## How to Report Issues

If you find a bug or have a feature request:
1. Search [existing issues](https://github.com/haenv/ha-smart-irrigation/issues) first
2. If it's new, open an issue with:
   - Your HA version and Python version
   - Reproduction steps (if it's a bug)
   - Expected vs. actual behavior
   - Relevant logs or screenshots
3. Feature requests: describe the use case and why it matters

---

## Contributing

Contributions are welcome! See the repository's CONTRIBUTING.md (if present) or open an issue to discuss before starting major work.
