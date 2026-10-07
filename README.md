# ZoneFlow Irrigation

**ZoneFlow turns Home Assistant into the irrigation controller.** Use the valves, pumps, sensors and weather hardware you already have — from simple Zigbee relays to more advanced flow and soil sensors.

Full documentation: **[zoneflowirrigation.com](https://zoneflowirrigation.com/)**

ZoneFlow works out when and how much each part of your garden needs water, from the plant, the soil, the weather and the rain, then runs the valve and tells you in plain words what it did and why. It also controls the climate of a greenhouse or indoor grow space. Only a valve switch is required; every sensor is optional and each one adds a capability.

<img src="docs/screenshots/hero.jpg" width="100%" alt="ZoneFlow dashboard on tablet and phone, in the garden">

## What it can do

- **Waters by need.** A light routine watering and an occasional deep soak per zone, from temperature tiers or an evapotranspiration curve, adjusted for the plant, soil, slope and mulch.
- **Uses the rain.** Rain credit from a rain gauge or a weather station (Ecowitt, Ambient Weather, Tempest, Davis and others), rain you enter by hand, a pause after heavy rain, a forecast skip and a frost guard.
- **Says why.** A plain-language status for every zone ("Skipped: the soil is wet (72%)"), phone notifications and a weekly summary.
- **Greenhouse and indoor zones.** Fans, vents, misters and a heater from an inside sensor, with several crops under one greenhouse.
- **Garden areas.** Group zones into the parts of your garden (Backyard, Front yard) and see them together on the cards and the dashboard.
- **Water use.** Litres and gallons per watering, for the last 30 days and for the year.
- **Safe by design.** Runtime caps, a stuck-valve watchdog, pump and flow checks and power-loss handling: a cycle always ends with the valve closed.
- **Easy to run.** Built-in dashboard cards and a ready-made dashboard, 19 languages, no YAML, and an optional AI-assisted setup.

## Install

1. In HACS: ⋮ → **Custom repositories** → add `https://github.com/Dreamer41/ha-smart-irrigation` as type **Integration**.
2. Find **ZoneFlow Irrigation** and click **Download**, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **ZoneFlow Irrigation**, and follow the screens.

Requires Home Assistant 2024.5 or newer. To install without HACS, copy `custom_components/zoneflow/` into `/config/custom_components/` and restart.

**First steps for a new zone:** [set the flow rate](docs/CALIBRATION.md) (the one number that must be right), press **Service Run 1 min** to check the valve, then let it run.

## Documentation

- **[zoneflowirrigation.com](https://zoneflowirrigation.com/)**: the full documentation.
- [Full guide](docs/GUIDE.md): what ZoneFlow does, sensors, dashboard, services, FAQ and the details behind this page.
- [Calibration](docs/CALIBRATION.md): flow rate, Zone Flow (litres) and the rain gauge.
- [Rain gauges and weather stations](docs/RAIN-GAUGES.md)
- [Greenhouse and indoor zones](docs/GREENHOUSE.md)
- [Weather Underground rain](docs/WEATHER-UNDERGROUND.md) (experimental)
- [AI-assisted setup](AI_SETUP.md): a guide an AI assistant follows to set ZoneFlow up for you.
- [Changelog](CHANGELOG.md) and [roadmap](ROADMAP.md).

## Help and feedback

Questions and bug reports: [GitHub issues](https://github.com/Dreamer41/ha-smart-irrigation/issues).

## License

[MIT](LICENSE).
