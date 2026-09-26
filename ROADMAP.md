# ZoneFlow roadmap

Ideas queued for upcoming releases.

## Next update (1.5.0)

### Built-in ZoneFlow dashboard card

A dashboard card shipped inside the integration, so dashboards update
themselves when ZoneFlow adds features — no YAML, no manual "update your
dashboard" steps.

- **Bundled, no separate install:** plain JavaScript (no build step) served
  and loaded by the integration itself.
- **Add once per zone:** Add card → ZoneFlow → pick the zone. The card
  finds that zone's entities through its device, so no entity IDs to type.
- **Updates itself:** new entities in a release appear on the card after
  the update.
- **Shows only what the zone has:** soil moisture only with a probe,
  deficit mode only where relevant, deep soak only when enabled.
- **Layout:** status first (valve, soil moisture, next run, last water),
  then manual controls (run now, snooze, service runs, Service Mode), then
  settings folded away (targets, thresholds, calibration, caps).
- Follows the zone's metric/imperial units.
- Normal HA cards keep working alongside it or instead of it.

Also in this release:

- **Entity categories:** mark sliders/calibration as *configuration* and
  lock/abort/diagnostic sensors as *diagnostic*, so the zone's device page
  and HA's auto-generated dashboards are tidy.

- **"Why?" status sensor:** one plain sentence per zone at the top of the
  card — "Next watering Mon 05:30, about 12 mm (3 mm rain credit)",
  "Skipped today: soil is wet", "Waiting: rain dry-down until Wed". Every
  gate that holds a run back says so, instead of skipping silently.
- **Fewer visible settings:** advanced sliders (custom ramp points,
  forecast thresholds, pump delays, pulse tuning) hidden by default — still
  there, switched on under the entity's settings. Together with the
  categories above, a zone's device page goes from ~60 entities to ~15.
- **Pause switch per zone:** "Paused until…" for holidays, repairs or
  winter, instead of disabling the integration.
- **Frost protection:** skip watering when frost is forecast or the
  temperature is below a set limit (protects pipes and drippers).
- **Notification levels per zone:** all / warnings only / none.

To work out when building:

- Automated screenshot test of the card in the sandbox (Chromium) — the
  Python test suite doesn't cover frontend code.
- Cache-busting when the card file changes (versioned URL).
- AI setup: offer the ZoneFlow card as the default dashboard, keep the
  YAML template (§9) for people who want to hand-build.
- Later, optionally: an auto-generated ZoneFlow dashboard ("strategy")
  with a tab per zone, reusing the same card.

## After that (1.6.0) — easier setup

- **Plant presets at setup:** pick Tomatoes / Chilis / Lawn / Fruit tree /
  Shrubs / Herbs… and the weekly targets, deep soak on/off, growth ramp,
  crop factor and pulse counts are pre-filled.
- **Flow-rate helper:** enter drippers per plant, litres/hour per dripper
  and bed area and it works out the flow rate — or, with a flow meter, run
  a 10-minute service run and it calculates it.
- **Weekly summary** (optional): water applied, rain received and next
  runs per zone, in one message.
- **Home Assistant Repairs:** problems shown in Settings → Repairs (valve
  unavailable, a sensor offline for days, flow rate never calibrated).
- **Diagnostics download** for bug reports.
- **Translations:** German, Dutch, French, Spanish, Italian, Finnish,
  Swedish, Polish, Portuguese (first batch — based on where Home Assistant
  users are). Covers entity names, setup screens and error messages via
  Home Assistant's translation files; the phone notifications and CSV log
  text are written in Python today and need their own translation step
  (following Home Assistant's language setting).

## Shipped

### 1.4.3

- **Service / check runs per zone:** Service Run 1 / 5 / 10 min buttons and
  a Service Mode switch (valve on until switched off, auto-off after 30 min
  by default with a phone alert). Same safety path as a real cycle; never
  counted as watering; minutes count toward the daily runtime safety cap.
- **A completed deep soak counts as the routine watering:** the routine
  interval restarts from it, so no full routine dose follows the next
  morning. (One direction only: the deep soak keeps its own clock.)
