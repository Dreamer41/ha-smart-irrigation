# Manual sandbox: click around a real Home Assistant, fully isolated

This runs an actual Home Assistant instance in Docker on your own PC, with
a fake valve, pump, rain gauge, and thermometer you control from sliders
and a counter in the UI. It has no connection whatsoever to your real
Home Assistant, your real network of entities, or your real valve/pump.
It's a completely separate HA install living in `sandbox/config/` on disk.

## Prerequisites

- Docker Desktop, installed and running.

## 1. Start it

From a terminal, in this `sandbox/` folder:

```
docker compose up -d
```

First boot takes ~30-60 seconds. Then open **http://localhost:8123**

## 2. One-time setup

1. Complete Home Assistant's normal onboarding (create a local account --
   this account only exists inside this sandbox container).
2. Go to **Settings → Devices & Services → Add Integration**, search for
   **ZoneFlow Irrigation**, and point it at the simulated entities (search
   by name in each picker -- exact `entity_id`s are listed for reference):
   - Valve: **Simulated Watering Valve** (`switch.simulated_watering_valve`)
   - Pump power sensor: **Simulated Water Pump Power**
     (`sensor.simulated_water_pump_power`)
   - Rain counter: **Simulated Rain Gauge Tips** (`counter.fake_rain_tips`)
   - Outdoor temperature sensor: **Simulated Outdoor Temperature**
     (`sensor.simulated_outdoor_temperature`)
   - Notify (optional): leave blank
   - CSV log path: `/config/zoneflow.csv` (writable inside the
     container)
   - Deep soak / routine times: whatever you like, doesn't matter here

That's it -- all 18 tunable numbers, the diagnostic sensors, the lock/abort
binary sensors, and the three buttons (Run Deep Soak, Run Routine
Irrigation, Reset Lock) now exist as real entities you can add to a
dashboard or drive from **Developer Tools → Actions**.

## 3. Things to try

- **Basic pulse test**: set "Simulated Pump Power" to something above your
  configured minimum (e.g. 800W), then call the `zoneflow.test_pulse`
  service (or press a Test Pulse button if you add one). Watch
  "Simulated Watering Valve" actually flip on and off in the dashboard in
  real time.
- **Rain response**: press "+1" on "Simulated Rain Gauge Tips" a few times.
  Watch the `Rain Past 24h` / `Rain Past 7d` sensors update, and watch
  `Next Irrigation Estimate` push out.
- **Heat response**: drag "Simulated Outdoor Temperature" up over several
  simulated days (see note below) and watch `3-Day Average Peak Temperature`
  and the routine watering size respond.
- **Full run**: call `zoneflow.run_deep_soak` or
  `run_routine_irrigation`. Watch `Irrigation In Progress` (binary_sensor)
  turn on, the valve pulse for real, and a row get appended to the CSV
  (`docker exec zoneflow-sandbox cat /config/zoneflow.csv`).
- **Lock behavior**: while one of the above is running, try calling the
  other service. It should be refused instantly (matching the YAML's
  behavior) rather than queuing/waiting.

**Time-based watchdogs (stuck valve, power loss, stale lock) run on real
wall-clock time here** -- e.g. the stuck-valve watchdog really will wait the
configured number of minutes. That's the trade-off vs. the automated pytest
suite (`tests/`), which fast-forwards simulated time to check these in
milliseconds. Use this sandbox for "does it look and feel right when I
click it", and the automated tests for "does every edge case actually
fire".

## 4. Updating after code changes

```
docker compose restart
```

The integration code is mounted straight from `../custom_components`, so
any change you (or I) make there is picked up on restart -- no rebuilding,
no copying.

## 5. Stop / reset

```
docker compose down
```

Config and entity history persist in `sandbox/config/` between runs. To
start completely fresh (re-run onboarding, wipe all history):

```
docker compose down
rm -rf config/.storage config/home-assistant_v2.db config/home-assistant.log*
docker compose up -d
```
