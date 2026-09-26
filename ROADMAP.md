# ZoneFlow roadmap

Ideas queued for upcoming releases.

## Next update

- An auto-generated ZoneFlow dashboard ("strategy") with a tab per zone,
  reusing the ZoneFlow card.
- The Status sentence with the expected amount ("Next watering Mon 05:30,
  about 12 mm").
- More languages, and corrections from native speakers.

## Shipped

### 1.5.0 — easier to use

- **Built-in ZoneFlow dashboard card**, served by the integration: add it
  per zone, it finds the zone's entities through its device, shows only
  what the zone uses, follows its units and picks up new features by
  itself.
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
