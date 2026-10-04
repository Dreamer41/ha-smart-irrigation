# Weather Underground rain (experimental, 1.6.1)

**Have a rain gauge? You don't need this.** ZoneFlow already reads your
gauge, and a zone with a gauge never uses Weather Underground.

This is an optional way for outdoor zones **without a rain gauge** to get
reasonably accurate local rain history, by borrowing the readings of private
weather stations near your garden. It is only used for **rain deduction**
(how much rain to credit against watering). It does not forecast, and it
does not replace the weather service used for skipping a watering before
rain.

Why bother: forecast services often use a station 20 km or more away. A
private station within a km or two is usually much closer to what fell in your
garden. But it is **not 100 % reliable**, and less so the further the
stations are from your zones. That is why it is marked experimental.

How useful it is depends on where you live: the USA and parts of Europe
have many private stations, so there is a good chance of one nearby; in
many other countries stations are few and far apart.

## Before you start: two checks, in this order

1. **First, check the map.** Open the map on
   [wunderground.com](https://www.wunderground.com/wundermap) and look for
   stations near your garden that report rain (look at "Precip"). Nearer
   is better: aim for within 1 km, at most 2 km. If there are none, stop
   here: this feature won't help you.
   Use a rain gauge, the manual rain entry, or nothing.
2. **Second, you need your own station to get the free API key.** Weather
   Underground only gives API keys to people who upload data. Register a
   station on wunderground.com and upload at least outdoor **temperature and
   humidity** (a rain gauge or a full weather station is not needed). The
   easy way is the
   [ha-weather-uploader](https://github.com/lancer73/ha-weather-uploader)
   HACS integration, which sends your Home Assistant sensors every few
   minutes. Once your station is uploading, the API key is in your Weather
   Underground account under API Keys.

There are three separate secrets: the **Station ID** and **Station Key**
(used by the uploader to send your data) and the **API key** (used by
ZoneFlow to read rain). ZoneFlow only needs the API key and stores it only
in its own entry: never in YAML, never in the log, and it is removed from
diagnostics downloads.

## Setting it up

1. Settings → Devices & services → Add integration → **ZoneFlow** →
   **Set up Weather Underground rain**. (It is offered once you have at
   least one zone, and only one per Home Assistant.)
2. Paste the API key and choose the search radius (0.5–2 km, default 1).
   ZoneFlow looks for stations around your Home Assistant home location and
   works out each distance itself.
3. Pick **1, 2 or 3 stations**. Each shows its distance and today's rain, so
   you can check the numbers look sensible. Stations over 1 km away are
   marked: for those, keep an eye on how their readings match the rain at
   your place for a while before trusting them.
4. For each outdoor zone without a rain gauge: the zone's **Configure** →
   **Weather Underground rain** → switch it on.

## How the rain figure is made

- **3 stations:** the middle reading, so one broken gauge can't fool it.
- **2 stations:** the **lower** reading. Too much rain makes ZoneFlow water
  too little, which hurts plants; too little only waters a bit more.
- **1 station:** used as is, with "lower confidence" shown.
- **No usable station:** nothing is added, and the zone acts as if it had no
  rain gauge. After 6 hours without usable data a Repairs issue appears; it
  clears by itself when data returns.

A station is left out when it hasn't reported for 2 hours, reports an
impossible jump, or has shown no rain for 24 hours while the others did
(a stuck gauge). When a station drops out or comes back, the figure is
re-anchored so it doesn't look like sudden rain.

## How often it checks

- Every **2 hours** normally.
- Every **10 minutes** from an hour before a watering until it has finished,
  so the 30-minute "raining now" check before and during a watering sees
  recent rain.
- Once at **23:55**, to catch the day's last rain (a station's total resets
  at midnight).

That is far below Weather Underground's limit for a free key (1500 calls a
day). Rain that arrives in a 2-hour lump counts for the daily rain credit,
the longer rain windows and deep soak, but never as "raining now". Stations
upload every few minutes, so "raining now" from Weather Underground lags
real rain by up to about 15 minutes.

## Is it good enough for your garden?

- Compare the **Rain today** sensor of the Weather Underground device, and
  each station's own sensor, with what you see.
- Watch the zone's **Forecast Skip Hit Rate**: it shows how often a skip for
  forecast rain was followed by real rain, measured with this rain data.
