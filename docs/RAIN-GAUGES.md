# Rain gauges and weather stations

ZoneFlow subtracts rain from what it waters, lets wet soil dry out first and
stops a watering when it starts raining. It needs one **rain gauge sensor**
per outdoor zone (Configure → Zone settings → *Rain gauge sensor*). Besides
the tip counter of a simple tipping-bucket gauge, ZoneFlow understands the
rain sensors of most weather stations. Tell it which kind of sensor you picked
under **Rain gauge sensor type**.

## Which type to choose

| Your sensor reports | Choose | Notes |
|---|---|---|
| A count that goes up by one with every tip of the bucket (an ESPHome or Zigbee tipping bucket, a counter helper) | **Tip counter** | Set the size of one tip on the zone's device page, *Rain Gauge mm per Tip*. |
| A running rain total in mm or inches that only goes up (lifetime, yearly, "total rain") | **Rain total** | Best choice when your station has one. |
| A rain total that starts again every day, week or month ("daily rain", "weekly rain") | **Rain total** | The drop back to zero is not read as rain. |
| The amount that fell since the previous reading (the Tempest *Precipitation* sensor: the previous minute) | **Rain per reading** | Every reading is added up, repeated readings included. |
| The current rain in mm (or inches) per hour ("rain rate", "precipitation intensity") | **Rain rate** | ZoneFlow adds the rate up over time, so it is less exact than a total. A reading counts for at most 15 minutes, so a sensor that stops updating does not keep adding rain. |
| Only "rain in the last hour" or "rain in the last 24 hours" | none of these | These go up and down, so they cannot be added up. Use a total, a per-reading amount or a rate from the same station instead, or the Weather Underground option. |

When a sensor is in inches (or centimetres), ZoneFlow converts it to
millimetres by itself. *Rain Gauge mm per Tip* is only used for a tip counter
and is hidden for the other types.

## Common stations

What the Home Assistant integrations offer (from their documentation and
source code; the names can differ by version, and none of this has been tested
with the hardware):

- **Ecowitt** (and the Froggit, Misol and Fine Offset clones): *Rainfall* (a
  lifetime total), *Daily, Weekly, Monthly and Yearly rainfall* (totals that
  start again) and *Rain rate*. Use *Rainfall* or *Yearly rainfall* as a
  **Rain total**; *Daily rainfall* works too.
- **Ambient Weather**: *Lifetime rain*, *Yearly, Monthly, Weekly and Daily
  rain*, *Event rain*, *Last 24 hours rain* (rolling, not usable) and an hourly
  rate. Use *Lifetime rain* or *Daily rain* as a **Rain total**.
- **WeatherFlow Tempest**: *Precipitation* is the amount over the previous
  minute, and *Precipitation intensity* is a rate. Use *Precipitation* as
  **Rain per reading**.
- **Netatmo rain module**: *Rain* (the latest measurement), *Rain last hour*
  (rolling, off by default) and *sum_rain_24*, which Home Assistant reports as a
  total that goes up. Netatmo describes it as the rain of the day, though some
  users report a rolling 24 hours: check it against your own gauge before
  relying on it. If it behaves like a daily total, use **Rain total**.
- **Davis WeatherLink**: usually a daily total and a rate; use the daily
  total as a **Rain total**.
- **Your own tipping bucket** (ESPHome, Zigbee, Tuya, rtl_433 over MQTT): a
  tip counter is a **Tip counter**; if it already reports millimetres, use
  **Rain total**.

## Good to know

- The first reading when ZoneFlow starts is a starting point, not rain: a
  lifetime total of 1,234 mm does not count as 1,234 mm of rain.
- ZoneFlow keeps a timestamped running total for **15 days**; every rain
  window (15 minutes up to 14 days) is the difference between two points of it.
- **Changing the sensor, or the type, starts the rain history again** (the rain
  windows and Rain Today begin at zero).
- Rain in the last 15, 30 and 60 minutes ("raining now") needs a sensor that
  reports often. A station that reports only every few minutes still works,
  but those short windows react more slowly.
- A sensor that reports the same value again (a steady rate, or 0.2 mm twice)
  is counted, on Home Assistant 2024.4 or newer.
- A zone without any rain sensor waters as if it never rains. You can still
  enter rain by hand (*Add Manual Rain*) or use Weather Underground.
