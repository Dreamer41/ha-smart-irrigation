# ZoneFlow roadmap

Ideas queued for upcoming releases. Nothing here is built yet.

## Next update (1.5.0)

### Service / check runs per zone

For checking emitters, flushing lines, finding leaks or showing someone the
system. None of these count as watering: they never set Last Routine
Irrigation or Last Deep Soak, never move the schedule, and never feed the
self-tuning.

- **Run 1 min / Run 5 min / Run 10 min buttons** on every zone.
- **Service Mode switch** (manual valve on/off) on every zone, for jobs
  that need the water running until you're done.

Design notes (from how `zoneflow.test_pulse` already works, which these
build on):

- Same safe path as a real cycle: takes the zone's lock and the shared-pump
  lock (so it waits for, or blocks, other zones on the same pump), runs the
  pump preamble/postamble, pump-power audit and stuck-valve watchdog, and
  always ends with the valve closed and confirmed — also on reload, restart
  or shutdown.
- Refused while the zone is already running a cycle, and a scheduled cycle
  can't start while a service run is on (it runs at its next scheduled time
  instead).
- **Service Mode has a safety auto-off** so a forgotten switch can't run the
  valve for hours: default 30 min, adjustable as a slider (e.g. 5–120 min),
  with a phone alert when it switches itself off. *(Decided.)*
- **Service minutes count toward the daily runtime safety cap** (it's still
  water through the pump, and the cap is a safety limit), but toward
  nothing that decides watering. *(Decided.)*
- Logged in the CSV as "Service Run" with the minutes run, clearly separate
  from watering runs.

AI setup and docs:

- Dashboard template: add the three run buttons and the Service Mode switch
  to every zone's Manual Controls card.
- Cheat sheet (§9a): "checking the drippers" — which button to press, and
  that it doesn't count as watering.
- Verification step (§8): use the 1-minute button instead of calling the
  test pulse service by hand.
- README: short section on service runs.
