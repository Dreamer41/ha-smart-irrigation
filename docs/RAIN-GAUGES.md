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
| The current rain in mm (or inches) per hour ("rain rate") | **Rain rate** | ZoneFlow adds the rate up over time, so it is less exact than a total. A reading counts for at most 15 minutes, so a sensor that stops updating does not keep adding rain. |
| Only "rain in the last hour" or "rain in the last 24 hours" | none of these | These go up and down, so they cannot be added up. Use a total or a rate sensor from the same station instead, or the Weather Underground option. |

When a total or a rate is in inches (or centimetres), ZoneFlow converts it to
millimetres by itself. *Rain Gauge mm per Tip* is not used for a total or a
rate and is hidden.

## Common stations

The names differ by brand and version; choose by what the sensor measures. This
is a guide, not a tested list.

- **Ecowitt** (and the Froggit, Misol and Fine Offset clones): the Ecowitt
  integration gives rain totals (daily, weekly, monthly, yearly, total) and a
  rain rate. Use the yearly or total rain if there is one, otherwise the daily
  rain, as a **Rain total**.
- **Ambient Weather**: daily, weekly, monthly and yearly rain totals, plus an
  event total. Use **Rain total** with the yearly or daily rain.
- **WeatherFlow Tempest**: an accumulated rain value for today and a rain rate.
  Use **Rain total** with today's accumulation, or **Rain rate**.
- **Davis WeatherLink**: daily and storm totals and a rate. Use the daily total.
- **Netatmo rain module**: it reports rain over the last hour and the last 24
  hours, which cannot be used. Try the Weather Underground option instead, or
  a total from another source.
- **Your own tipping bucket** (ESPHome, Zigbee, Tuya, rtl_433 over MQTT): a
  tip counter is a **Tip counter**; if it already reports millimetres, use
  **Rain total**.

## Good to know

- The first reading when ZoneFlow starts is a starting point, not rain: a
  lifetime total of 1,234 mm does not count as 1,234 mm of rain.
- **Changing the sensor, or the type, starts the rain history again** (the rain
  windows and Rain Today begin at zero).
- Rain in the last 15, 30 and 60 minutes ("raining now") needs a sensor that
  reports often, as a tipping bucket does. A station that reports only every
  few minutes still works, but those short windows react more slowly.
- A zone without any rain sensor waters as if it never rains. You can still
  enter rain by hand (*Add Manual Rain*) or use Weather Underground.
