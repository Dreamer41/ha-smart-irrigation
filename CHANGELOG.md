# ZoneFlow Changelog

All notable changes to this project are documented here.

For detailed release notes and upgrade instructions, see the **docs/** folder for each version.

## [Unreleased]

- **Changed (docs)**: the README is now a short introduction that points to the website and to the guides in `docs/`. The long README moved, unchanged, to [docs/GUIDE.md](docs/GUIDE.md). New [docs/CALIBRATION.md](docs/CALIBRATION.md): how to set the flow rate, Zone Flow (litres) and the rain gauge
- **New**: **garden areas**. Each zone can be put in a part of the garden of your own naming (the **Garden Area** dropdown in the zone's settings on its card, with the names already in use and *New area…*, or **Configure → Garden area** with a dropdown of the names in use; for example *Backyard* or *Front yard*). The overview card groups the zones under their area's heading (zones with no area under *Other*), and the auto-generated dashboard (`strategy: custom:zoneflow`) gets one tab per area with its zones side by side. A crop follows its greenhouse's area. Nothing changes for zones that have no area
- **Changed**: a **deep soak that comes due soon after a routine watering now waits for the next routine slot and replaces that routine**, instead of watering again the next day. It waits at most one routine interval (3 or 4 days) past its due date. A manual *Run Deep Soak Now* still runs at once, and a zone that has never done a deep soak is not affected

## [1.6.5] — Water use in litres and rain from weather stations

- **New**: **rain from weather stations**. A new setting, **Rain gauge sensor type** (Configure → Zone settings), tells ZoneFlow what the rain sensor reports: a **tip counter** (as before), a **rain total** in mm or inches (lifetime, daily or weekly, as from Ecowitt, Ambient Weather or Davis), a **rain rate** in mm/h, which is added up over time, or **rain per reading** (the amount since the previous update, as the Tempest *Precipitation* sensor reports it). Only the increase of a total counts, so a reset at midnight is not rain, and the tip size setting is hidden for totals and rates. Changing the sensor or the type starts the rain history again. New guide: [docs/RAIN-GAUGES.md](docs/RAIN-GAUGES.md)
- **New**: **water use in litres (gallons)**. A new **Zone Flow** setting (litres per minute the zone's valve gives) turns valve minutes into litres. Set it under **Configure → Zone flow** (heads x flow per head), or it is set when you work out or measure the flow rate. The zone card shows the **last watering as mm and litres** (new **Last Water Volume** sensor), and new **Water Used, Past 30 Days** and **Water Used This Year** sensors (calendar year, from 1 January) keep a daily record of about 400 days. A flow meter's measured litres are used when there is one. Estimates only, never used for watering decisions; zones without Zone Flow or a flow meter show mm only, and earlier watering stays in mm
- **Fixed**: **Rain Today** showed a sensor's whole history as rain today when rain tracking started on a sensor that already held a count (a new zone, a switched sensor, or a sensor that came online after startup)
- **Fixed**: a rain total that starts again every day or week could be taken for a sensor glitch on a heavy-rain day and under-count the rain

## [1.6.4] — Rain gauge fix, measure flow by volume

- **Fixed**: **rain amounts that were too high** on zones with a rain gauge. The rain windows keep cumulative millimetres (tips × mm per tip), so a calibration that differed from the one the samples were recorded with — the *Rain Gauge mm per Tip* slider moved, or a restart that read the default before the saved value was restored — added (all tips so far) × (the difference) on the next tip: about 4 mm of rain that never fell with 436 tips and 0.309 vs 0.300. The stored samples are now rescaled to the calibration in use. A wrong amount already recorded fades out of the 14-day window by itself
- **New**: **Configure → Flow rate: measure it by the litres a service run gave** — for zones without a flow meter. Press a Service Run button (15 min is the most accurate), catch or read the water (bucket, barrel, water meter), and enter the minutes, litres and wet area; ZoneFlow sets the Emitter Flow Rate Calibration. The result is the zone's **average**: ZoneFlow has one rate per zone, so for a precise result every emitter on a zone's valve should be the same type and flow. Put different emitters on separate valves (zones); the plants on the weaker emitters of a mixed zone get less than the average shown. The emitter-count option now says it assumes equal emitters
- **Fixed**: deleting the Weather Underground entry now switches "use Weather Underground" off in the zones that used it, so manual rain is offered again (before, those zones kept hiding it and rain read 0)
- **Changed**: the integration's `iot_class` is now `cloud_polling`, since Weather Underground calls a cloud service (optional)

## [1.6.3] — 15-minute service run

- **New**: a **Service Run 15 min** button next to the 1, 5 and 10 minute ones, for a longer flow-calibration test. Like the others it is never counted as watering and respects the daily safety cap

**Update your dashboard**: the zone card shows the new button by itself. A hand-made dashboard can add `button.<zone>_service_run_15_min`

## [1.6.2] — Stuck-probe protection, hardening and tidier greenhouse deletion

- **Fixed**: a soil-moisture probe stuck on "dry" (or reading dry because it is out of the soil) that keeps reporting made the zone water a **full** interval dose **every morning** — about four times the weekly target in a four-week simulation. A run a dry probe brings forward now gives only the share of the dose the days since the last watering call for (at least a quarter), so even a stuck probe stays near the weekly target

- **Fixed**: Weather Underground answering with something that isn't a report (a list, a string, NaN, infinity, a missing key) no longer raises an error in the answer parser or the station-picking form; NaN and negative totals are never counted as rain
- **Fixed**: a hand-entered rain amount that isn't a finite number is refused; a zone that names itself as its greenhouse is just a zone
- **Changed**: deleting a greenhouse zone now switches off its fans, misters and heater and closes its vents (nothing controls them any more); a reload or restart still leaves them alone
- **Translations**: the "nothing is on hold" message of Resume Automatic in every language

---

## [1.6.1] — Rain without a gauge, Resume Automatic and a ready-made dashboard

- **New**: **Weather Underground rain (experimental)** — an outdoor zone **without a rain gauge** can borrow rain from 1-3 private weather stations within 2 km (nearer is better). One shared entry for the whole Home Assistant (Add integration → ZoneFlow → Set up Weather Underground rain), the station readings combined (3 stations: the middle one, 2: the lower one, 1: as is), polled every 2 hours and every 10 minutes around a watering. Only for rain deduction, not 100 % reliable. Read [the guide](docs/WEATHER-UNDERGROUND.md) first: check the Weather Underground map for stations nearby, and note the free API key needs your own station uploading temperature and humidity. Not for zones with a rain gauge
- **New**: **manual rain** — enter rain read from a simple gauge (Manual Rain number + Add Manual Rain button, or the `zoneflow.add_rain` service), up to 14 days back; hidden on zones with a gauge or Weather Underground
- **New**: **Forecast Skip Hit Rate** sensor — each watering skipped for forecast rain is judged 48 hours later against the rain that really fell
- **New**: **Resume Automatic** button for greenhouse and indoor zones ends a manual hold at once
- **New**: **Auto Resume** switch and **Auto Resume After** (0.5-24 h) — a device you switched by hand goes back to automatic after that time, or waits for the button when the switch is off
- **Changed**: Auto Resume After replaces **Manual Hold Time**; your old value is carried over, rounded up to the next half hour ("0" becomes 0.5 h)
- **New**: a heater switched on by hand is taken back once the inside temperature goes above the vent temperature, whatever the hold setting
- **New**: **several crops in one greenhouse** — Add integration → ZoneFlow → *Add a crop to a greenhouse*: each crop has its own valve, soil probe, plant and schedule and uses the greenhouse's climate and inside sensors (read live). Crops are connected via their greenhouse in the device list, listed on the greenhouse's card, under it in the overview card, and on its tab in the auto-generated dashboard. Zones set up the old way join a greenhouse under Configure → Greenhouse. Deleting a greenhouse leaves its crops working on their own
- **Changed**: a greenhouse or indoor zone without climate devices no longer shows the Greenhouse Status sensor and Greenhouse Control switch
- **New**: **auto-generated dashboard** — `strategy: {type: custom:zoneflow}` builds an overview tab and one tab per zone
- **Changed**: adding a second zone now starts with a small menu (Add a zone / Set up Weather Underground rain)
- **Fixed**: a test of two zones sharing a pump was timing-dependent on Windows
- **Tests**: full suite passes

See [docs/1.6.1-RELEASE-NOTES.md](docs/1.6.1-RELEASE-NOTES.md) for details and upgrade instructions.

---

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
