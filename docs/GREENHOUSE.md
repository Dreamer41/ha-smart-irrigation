# Greenhouse and indoor zones (ZoneFlow 1.6)

A ZoneFlow zone can be **outdoor** (how ZoneFlow has always worked),
**greenhouse** or **indoor**. Greenhouse and indoor zones can control the
climate of the space — fans, vents, misters and a heater — as well as water
it. The valve is optional: a zone with climate devices and no valve is a
**climate-only zone**. Existing zones stay outdoor zones; nothing changes for
them.

Greenhouse and indoor zones have no rain gauge and no weather forecast (there
is a roof). If real rain does reach your plants, set the zone up as outdoor.

## Watering a greenhouse or indoor zone

Pick a **valve** and the zone waters in the same way as an outdoor zone,
with everything under *Watering settings*:

- the **soil-moisture probe** (optional): dry soil waters early, wet soil
  skips, with the same dry and wet thresholds as outdoors;
- soil type, drainage, slope, irrigation method, the routine and deep soak
  times (or sunrise/sunset offsets), the growth ramp, pump power sensor,
  flow meter and the pump sharing between zones;
- the weekly water targets, ET curve, mulch, deficit mode, pause and
  snooze, and the service runs.

What is different under a roof: **no rain credit and no forecast** (no rain
gauge or weather service is asked for, so Weather Underground rain and
manual rain don't apply), and the hot / cool / normal water target and the
**frost guard** follow the **inside temperature** instead of an outside one
(in an unheated greenhouse, watering still waits while it is freezing
inside).
A probe is the best way to water a greenhouse: rain never tops it up, so
the soil's own reading is the truth.

## Several crops in one greenhouse

Each crop is its own zone, with its own valve, soil probe and watering
settings. The climate (fans, vents, misters, heater) belongs to **one**
zone, and a fan, vent, mister or heater can't be in two zones. So:

1. Add one **greenhouse** zone for the climate (call it, say, "Greenhouse
   climate"): the inside temperature sensor and the climate devices, and no
   valve.
2. Add one **greenhouse** zone per crop ("Tomatoes", "Peppers"...): pick
   that crop's valve and probe, and the **same inside temperature sensor**.
   Leave the climate devices empty. Each crop has its own plant type, soil,
   schedule and thresholds.

Sensors can be shared between zones; valves and climate devices can't. Zones
that share a pump should share the same *Pump ID* so they don't open
together. The overview card and the auto-generated dashboard show every zone
as its own row and tab.

## Set it up

**Settings → Devices & Services → Add Integration → ZoneFlow Irrigation**,
then pick *Greenhouse* or *Indoor* under **Where it grows**. ZoneFlow asks for:

1. **Sensors and climate devices**, all optional:
   - *Inside temperature* — needed for any device, and used for watering too.
   - *Backup inside temperature sensors* — see "Protecting the plants" below.
   - *Inside humidity* — for misting by humidity and for humidity venting.
   - *Light* (illuminance or irradiance) — only to mist by light.
   - *Outside temperature* — so ventilation never pulls in hotter air.
   - *Fans* (`switch`, `input_boolean`, `fan`), *Vents* (`cover`, `switch`,
     `input_boolean`), *Misters* (`switch`, `input_boolean`, `valve`),
     *Heaters* (`switch`, `input_boolean`, `climate`). Several of each, of
     mixed kinds, are fine. A simple space heater on a smart plug or relay
     (Shelly, Sonoff and the like) is a `switch`; a `climate` heater is
     switched between heat and off, and its own thermostat setting still
     applies.
2. **Does this zone water?** Pick the valve, or leave it empty for a
   climate-only zone (which needs at least one device).
3. **Watering settings** (only with a valve), then the **climate**, which
   fills in the starting temperatures (tropical, hot summers, temperate,
   cool summers).

You can add or change sensors, backup sensors and devices at any time under
**Configure → Valve, sensors and climate devices**, and change the zone type under
**Configure → Zone type**. Nothing is deleted: settings a zone doesn't use
are hidden and come back when it does.

## What it does

Every 30 seconds, and whenever a sensor changes, ZoneFlow compares the inside
readings with the zone's settings:

- **Cold** — the heater comes on below *Heater On Below* and goes off again
  *Climate Hysteresis* above it. While heating, vents and fans stay closed.
- **Warm** — vents open at *Vents Open At* (to *Vent Open Position*); fans
  join at *Fans On At*. Humidity above *Ventilate Above Humidity* opens things
  up too, but not while heating and not when it would chill the space.
- **Outside air check** — vents and fans only open when the outside air is
  cooler than inside by at least *Outside Air Margin*, and close again when it
  is no longer cooler. Without an outside sensor, this check is skipped.
- **Misting** — short pulses (*Mist On Time*, then *Mist Off Time*) when the
  temperature, humidity or light trigger is met (*Misting Trigger* chooses
  which), never below *Mist Minimum Temperature*, at or above *Mist Stop
  Humidity*, while the heater is on, in frost, or at night unless *Mist At
  Night* is on. *Max Misting Per Hour* is a hard cap.
- **Minimum run times** keep devices from short-cycling: fans 2 minutes,
  vents 3, heater 5.

The **Greenhouse Status** sensor says what it is doing and why, **Inside VPD**
shows the vapour pressure deficit (for information), **Misting Today** and
**Ventilation Allowed** complete the picture, and **Greenhouse Control**
pauses the whole climate engine for maintenance (devices are left as they
are, except a heater ZoneFlow switched on, which goes off). The ZoneFlow card shows all
of it, with the climate settings under their own groups.

## Settings

| Setting | Default (temperate) | Range |
|---|---|---|
| Heater On Below | 10 °C | 0–30 |
| Vents Open At | 25 °C | 10–40 |
| Fans On At | 28 °C | 10–45 |
| Climate Hysteresis | 1.5 °C | 0.5–5 |
| Outside Air Margin | 1 °C | 0–10 |
| Ventilate Above Humidity | 85 % | 50–100 |
| Mist On Above Temperature | 30 °C | 15–45 |
| Mist On Below Humidity | 50 % | 20–90 |
| Mist Light Level | 40 000 lx | 1 000–150 000 |
| Mist Minimum Temperature | 18 °C | 5–30 |
| Mist Stop Humidity | 85 % | 50–100 |
| Mist On Time / Mist Off Time | 10 s / 120 s | 3–300 s / 10–3600 s |
| Max Misting Per Hour | 10 min | 1–60 |
| Vent Open Position | 100 % | 10–100 |
| Auto Resume After | 1 h | 0.5–24 h (used while **Auto Resume** is on) |
| Sensor Offline After | 4 h | 1–24 |

The climate you pick at setup seeds the heater, vent, fan and misting
temperatures: tropical 15 / 28 / 31 / 32 °C, hot summers 8 / 27 / 30 / 30,
temperate 10 / 25 / 28 / 30, cool summers 8 / 22 / 26 / 28. The settings form
refuses combinations that contradict each other (heating must end well
before venting starts, fans at or after vents, the misting humidity trigger
below the humidity stop).

## When you switch a device yourself

If you switch a role's device yourself -- in Home Assistant, with a wall
button, in the device's own app -- or another automation does, ZoneFlow
leaves that role alone and says so in the status. A device coming back
from "unavailable" is not treated as someone switching it.

- **Auto Resume** on (the default): ZoneFlow takes the device back after
  *Auto Resume After* (0.5–24 h, default 1 h), so a forgotten device goes
  back to automatic.
- **Auto Resume** off: the device stays as you left it until you press
  **Resume Automatic**.
- **Resume Automatic** ends every hold in the zone at once.

Two safety limits apply whatever the setting: a mister you switch on is
switched off after *Max Misting Per Hour*, and a heater you switch on is
taken back once the inside temperature goes above the vent temperature, so
a forgotten heater can't overheat the greenhouse.

(1.6.1 replaced the old *Manual Hold Time* in minutes: your setting was
carried over, rounded up to the next half hour; "0" became 0.5 h.)

## Protecting the plants

**If the inside temperature sensor fails** (unavailable, no report for
*Sensor Offline After* -- 4 hours unless you change it -- or an impossible
value) for 2 minutes, ZoneFlow switches to its
failsafe: misters off immediately; vents and fans follow **Sensor
Failsafe** (*Open vents, fans on* / *Close vents, fans off* / *Leave as they
are*; the default follows your climate); the heater follows **Heater
Failsafe**:

- **Off**,
- **On part of the time** — 10 minutes in every 20, whatever the weather, or
- **Part of the time while cold outside** — the same, but only while the
  outside temperature is below *Heater On Below* (the default when you have an
  outside sensor; off when you don't).

While that heater is allowed to run because it is cold outside, the vents
stay shut and the fans off, whatever *Sensor Failsafe* says.

You get a phone message when the failsafe starts and when it ends, and a
Repairs issue after 10 minutes. Shorter dropouts change nothing.

**Backup sensors.** Add one or more extra inside temperature sensors. If the
main one stops, ZoneFlow carries on with the first backup that works and
tells you. If the main sensor and a backup disagree by more than 5 °C for 30
minutes, you are told that too, because one of them is wrong.

**Misting is defensive by design.** Pulses only, each "off" is confirmed; a
mister that won't switch off is retried once, then misting halts with a
Repairs issue and a phone message until you press **Reset Irrigation Lock**;
a mister found on past its pulse is forced off; the hourly cap is enforced.

**Also built in:** nothing switches during Home Assistant's startup grace
(about 2 minutes); a heater ZoneFlow switched on is switched off again when
the zone is unloaded or Home Assistant stops (one you switched on is left
alone).

### What ZoneFlow cannot do for you

Switching a heater from Home Assistant is convenient, not a safety system.
If you have a heater:

- **Put a hardware frost thermostat in the heater's power line** — or use a
  heater with its own thermostat and over-temperature cut-out — so frost
  protection and a hard maximum survive a crashed Home Assistant, a dead
  Wi-Fi link or a failed sensor.
- **Add a backup temperature sensor placed away from the main one**: the
  other end of the house, at plant height, out of direct sun and away from
  the heater and the vents. One stuck or badly placed sensor can otherwise
  blind the whole control.

## Troubleshooting

- *"starting"* in the status: the startup grace; it passes in about 2 minutes.
- *"A fan, vent, mister or heater needs the inside temperature sensor"*: add
  the inside sensor first.
- *A device is not responding* (Repairs): ZoneFlow asked twice and the device
  did not report the change; check the device.
- *Misting halted* (Repairs): a mister did not switch off; check it, then
  press **Reset Irrigation Lock**.
- A device is left alone for an hour: you switched it (or something else
  did); see "When you switch a device yourself".
- *Failsafe* when nothing is wrong: a sensor that only reports when its
  value changes can stay quiet for hours in a steady room. Raise *Sensor
  Offline After*.
