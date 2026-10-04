# ZoneFlow roadmap

Ideas queued for upcoming releases.

## 1.6.1 (planned)

**Rain from nearby Weather Underground stations (experimental).** An opt-in rain source
for outdoor zones without a rain gauge. It is marked *experimental*: the
data is not 100 % accurate, but it is closer to the ground than model data
such as Open-Meteo, which is not measured by gauges.

- **Check first, key second.** The docs and the setup screen start with:
  look at the Weather Underground map for stations within about 2 km that
  report rain. If there are none, stop; use your own gauge, the manual
  entry below, or the forecast.
- **Getting a key.** Register your own station on wunderground.com and
  upload outdoor temperature and humidity (a full weather station or a rain
  gauge is not needed). The easy way is the
  [ha-weather-uploader](https://github.com/lancer73/ha-weather-uploader)
  HACS integration (about every 5 minutes); a plain web-request example goes
  in the docs too. The API key comes from the WU account. Three separate
  secrets: Station ID and Station Key (to upload), API key (to read rain;
  the only one ZoneFlow stores, in the config entry, never in YAML).
- **Close stations only.** A small radius (a few km); stations further away
  are rejected because their rain is not local. If none is close enough, the
  feature says so and stays off.
- **Several stations.** With 2-3 close stations ZoneFlow uses the median of
  their rain totals, so one broken gauge cannot fool it. One station is
  allowed but flagged as lower confidence. Silent, stuck or outlying
  stations are ignored.
- **Polling** about every 2 hours, plus once just after local midnight for
  the day's final total. Feeds the same rain credit as a gauge; the status
  shows where the rain figure came from.
- **Look at the data.** Each station's current reading is shown at setup and
  in the status so the person can check it looks right before trusting it.
- **Manual rain entry** for old-style gauges you read and empty yourself: a
  number field plus a button, and a service for automations. The entry is
  timestamped and counts as rain credit, without double counting rain that
  a station or sensor already reported for the same period.
- **Did the skip pay off?** A small journal records, for each watering
  skipped because rain was forecast, how much rain actually came (station
  or manual entry).
- An auto-generated ZoneFlow dashboard ("strategy") with a tab per zone,
  reusing the ZoneFlow card.

## Next update

- The Status sentence with the expected amount ("Next watering Mon 05:30,
  about 12 mm").
- Greenhouse: a **Resume automatic** button that ends a manual hold at once
  (today the hold ends by itself after Manual Hold Time).
- Greenhouse: device names ("Fans", "Vents", "Heater", "Misting") translated
  inside the notifications and the status, not only the sentences around
  them.
- More languages, and corrections from native speakers (the 1.6 texts are
  machine translated).

## Shipped

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
