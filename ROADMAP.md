# ZoneFlow roadmap

Ideas queued for upcoming releases.

## Next update

- Valve overlap for zones that share a pump: the next zone's valve opens a few
  seconds before the running zone's closes, so the pump never pushes against
  closed valves and the pipes do not bang.
- A plant inventory across all zones.
- Greenhouse: device names ("Fans", "Vents", "Heater", "Misting") translated
  inside the notifications and the status, not only the sentences around
  them.
- More languages, and corrections from native speakers (the 1.6 texts are
  machine translated).

## Shipped

### Next release (on dev-1.7.4)

- Longest Valve Open Time and the recommended backup timer for the valve's own auto-off.
- Water now with minutes splits into pulses like the zone's own watering.
- When Soil Gets Wet During Watering (finish, or stop at the wet level) for zones with a soil probe.
- Former fixed values as settings: deficit range 30-100, minimum pulse lengths, self-tuning switch and sliders, summary and reminder times at setup; the due buffer follows the last run's length.
- My Valve's Own Timer, the next watering previewed in Why?, a simpler Settings popup, a "?" on every setting (website docs), a valve test at the end of zone setup.

### 1.7.3 — days between waterings, Watering time, Delete zone, Valve Overlap

- Days between routine waterings (normal and hot) and the rain that starts the dry-down are settings.
- Watering time and Delete zone on the zone card.
- Valve Overlap for zones that share a pump.

### 1.7.2 — watered by the rain, drag and drop plants

- Rain that covers the next routine dose (or a deep soak) counts as the watering; Mark Deep Soak Done for zones with no rain measuring.
- Drag and drop plants between zones on the overview card, with a confirmation.
- The Status sentence says the estimated amount of the next watering.

### 1.7.1 — Water now fix, quick setup and nursery plants

- Water now / Run routine now waters at once, even when the routine is not due.
- Quick setup for a new outdoor zone: the valve, how the water is delivered and
  how much it gives; the rest from the plant type and what was found.
- Nursery plants followed to "ready to move": stage, badge and a phone message.

### 1.7.0 — areas, plants and easier setup

- Areas that share a rain gauge, thermometer, weather and phone, with their
  own Pause and Snooze Today; a Where is this? dropdown on every zone card.
- Plants with a history (add, move, make main, remove, notes); copy settings
  and presets; Start from when adding a zone.
- Check my setup, guided Calibrate, Water now for N minutes, Why?, a Simple
  view, My Garden summary, one-click dashboard, Fix buttons in Repairs,
  likely entities in setup, buttons on phone messages.
- A greenhouse and its crops are a group of their own, with Pause and Snooze
  Today for the whole greenhouse; a deep soak waits for the next routine slot.

### 1.6.5 — water use in litres, rain from weather stations

- Zone Flow (litres per minute), Last Water Volume, Water Used Past 30 Days and
  This Year; Configure → Zone flow.
- Rain gauge sensor type: tip counter, rain total (lifetime, daily, weekly),
  rain rate or rain per reading, for Ecowitt, Ambient Weather, Tempest and
  similar stations.

### 1.6.4 — rain gauge fix, measure flow by volume

- Rain from a gauge no longer jumps when the mm-per-tip calibration differs
  from the one the stored samples were recorded with.
- Configure → Flow rate: measure it by the litres a service run gave.
- Deleting the Weather Underground entry gives manual rain back.

### 1.6.3 — 15-minute service run

- A Service Run 15 min button for longer flow-calibration tests.

### 1.6.2 — stuck-probe protection and hardening

- A soil probe stuck on "dry" can no longer flood a zone: a run it brings
  forward gives the elapsed days' share of the dose.
- Weather Underground answers that make no sense are no data, not errors.
- Deleting a greenhouse switches its fans, misters and heater off and closes
  its vents.

### 1.6.1 — rain without a gauge, Resume Automatic and a ready-made dashboard

- **Weather Underground rain (experimental)**: an outdoor zone without a rain
  gauge can borrow rain from 1-3 private stations within 2 km (nearer is
  better), set up once for the whole Home Assistant. Only for rain
  deduction; the docs say to check the Weather Underground map first, and
  that the free API key needs your own station uploading temperature and
  humidity. Polls every 2 hours, every 10 minutes around a watering.
- **Manual rain**: enter rain read from a simple gauge (number + button, or
  the `zoneflow.add_rain` service), up to 14 days back.
- **Forecast Skip Hit Rate**: judges each watering skipped for forecast rain
  48 hours later against the rain that really fell.
- **Resume Automatic**: a button that ends a manual hold at once, an **Auto
  Resume** switch and **Auto Resume After** (0.5-24 h) replacing Manual Hold
  Time; a heater switched on by hand is taken back when it gets too hot.
- **Several crops in one greenhouse**: each crop its own valve, probe and
  schedule, sharing the greenhouse's climate and sensors.
- **Auto-generated dashboard**: `strategy: {type: custom:zoneflow}` gives an
  overview tab and one tab per zone (per greenhouse, with its crops).

### 1.6.0 — greenhouse and indoor climate control

- **Zone types**: outdoor (as before), **greenhouse** and **indoor**; change
  it later without losing anything. Existing zones stay outdoor.
- **Climate control**: fans, vents, misters and a heater, any number of
  each, from switches, input booleans, fans, covers, valves and climate
  entities, driven by an inside temperature sensor and optionally humidity,
  light and outside temperature.
- **Climate-only zones**: the valve is optional.
- **Outside-air check**: ventilation never pulls in hotter air.
- **Misting** by temperature, humidity or light, in short supervised pulses
  with an hourly cap and a halt-and-alert if a mister won't switch off.
- **Failsafes**: sensor failsafe for vents and fans, a part-time heater
  failsafe (off / part of the time / part of the time while cold outside),
  and **backup inside temperature sensors**.
- **Manual hold**: a device you switch by hand is left alone for a while.
- **Card and overview** show climate zones; **settings appear only when the
  hardware they act on is set up**; sensors and devices can be added later.
- All new texts in the 19 languages; new
  [greenhouse guide](docs/GREENHOUSE.md) and AI setup section.

### 1.5.1

- **Mulch**: a Mulched / Not Mulched select with a **Mulch ET Adjustment**
  slider (-50% to +70%) for bare-soil evaporation.
- **Mark Watered** button for manual watering; one-tap card buttons; hover
  tips on settings.

### 1.5.0 — easier to use

- **Built-in ZoneFlow dashboard card**, served by the integration: add it
  per zone, it finds the zone's entities through its device, shows only
  what the zone uses, follows its units and picks up new features by
  itself; the journal and settings open as popups.
- **ZoneFlow overview card**: every zone in one table — status, next and
  last watering, water now — sorted by name or next watering, an icon per
  zone; a click opens the zone's full card; an Add zone button.
- **Status sensor** ("why"): one sentence per zone — watering now, what it
  decided today and why, or when it waters next.
- **Tidy device page**: settings under Configuration, technical sensors
  under Diagnostic, unused settings hidden; **Download diagnostics**.
- **Pause** switch and **Paused Until** date.
- **Frost guard** with hourly re-checks (temperature sensor, or the
  weather entity's reading).
- **Notifications** per zone: all / warnings only / none; **weekly
  summary** per phone.
- **Repairs**: valve unavailable, sensor offline for days, missing notify
  target, uncalibrated flow rate.
- **Plant presets** at setup and a **flow-rate helper** (from the
  emitters, or measured with a flow meter).
- **Languages**: German, Dutch, French, Spanish, Italian, Finnish,
  Swedish, Polish and Portuguese, for entity names, setup screens, the
  Status sentence, notifications, the weekly summary and the card.

### 1.4.3

- **Service / check runs per zone:** Service Run 1 / 5 / 10 min buttons and
  a Service Mode switch (valve on until switched off, auto-off after 30 min
  by default with a phone alert). Same safety path as a real cycle; never
  counted as watering; minutes count toward the daily runtime safety cap.
- **A completed deep soak counts as the routine watering:** the routine
  interval restarts from it, so no full routine dose follows the next
  morning. (One direction only: the deep soak keeps its own clock.)
