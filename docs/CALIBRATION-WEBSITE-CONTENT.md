# Website Content: Calibration (Plain Language)

**Purpose**: Copy for the ZoneFlow website explaining how to calibrate a zone. Plain language, no code. Written so it can be pasted section by section and edited. Menu names are the ones in Home Assistant (Settings → Devices & services → ZoneFlow → the zone → **Configure**).

---

## Headline

### One Number Decides How Much Water Your Plants Get. Here's How To Get It Right.

---

## Short Explanation (Elevator Pitch)

ZoneFlow works out how much water each plant needs, then turns that into minutes with the valve open. To do that it needs to know one thing about your watering system: **how much water ends up on the ground every minute**. That is the *flow rate calibration*. Get it right and every watering is the right size. This page shows three easy ways to find it, from "read the packaging" to "catch the water in a bucket".

---

## What Calibration Means

Imagine your valve is open for one minute. How deep a layer of water do your drippers or sprinklers put on the soil in that minute? Gardeners measure that depth in millimetres (or inches). A typical drip line puts about a quarter of a millimetre per minute. ZoneFlow shows it as **Emitter Flow Rate Calibration**.

- **Too low a number**: ZoneFlow thinks the system is weak, runs the valve longer than needed, and **overwaters**.
- **Too high a number**: ZoneFlow thinks the system is strong, runs the valve shorter than needed, and **underwaters**.

Until you set it, ZoneFlow uses a typical value and reminds you in Home Assistant's Repairs list. It is the one setting that really must be right.

---

## Pick Your Method

| You have | Use | How accurate |
|---|---|---|
| Drippers or sprinklers with the flow printed on the packaging | **Calculate it from the emitters** | Good, if the packaging numbers are true for your pressure |
| A bucket, a barrel or a water meter | **Measure it by the litres a service run gave** | Best, no special hardware |
| A flow meter on the zone | **Measure it with the flow meter** | Best, fully automatic |

All three are under **Configure → Flow rate**.

---

## Method 1: Calculate It From Your Emitters

You need three numbers:

1. **How many emitters** (drippers, sprinkler heads) the zone's valve feeds.
2. **How much one emitter gives**, in litres per hour (or gallons per hour). It is printed on the emitter or its packaging, for example *2 L/h*.
3. **The area they water**, in square metres (or square feet). For drippers at single plants, add up the small wet patches around each plant, **not** the whole bed.

Open **Configure → Flow rate: work it out from the emitters**, enter the three numbers, and ZoneFlow does the maths and sets the calibration.

**Example**: 50 drippers of 2 L/h each water 20 m² of bed.
That is 100 L per hour on 20 m², which is about **0.08 mm per minute**.

*Good to know*: packaging numbers are for ideal pressure. A long line, a weak pump or a clogged filter gives less. If you can, check with Method 2.

---

## Method 2: Measure It With a Bucket (Recommended)

No equipment needed except something to catch water.

1. Press **Service Run 15 min** on the zone. (It runs the valve for 15 minutes and does **not** count as a watering. A longer run is more accurate. 5 or 10 minutes also work.)
2. Catch the water that comes out: a bucket or barrel under the emitters, or read the difference on a water meter before and after.
3. Open **Configure → Flow rate: measure it by the litres a service run gave**.
4. Enter the **minutes** the valve was open, the **litres** you caught, and the **area** the water falls on.

ZoneFlow works out the calibration for you.

**Example**: 15 minutes gave 36 litres on 10 m².
36 litres ÷ 10 m² ÷ 15 minutes = **0.24 mm per minute**.

---

## Method 3: Let a Flow Meter Do It

If the zone has a flow meter that reports litres (a pulse meter, for example), choose **Configure → Flow rate: measure it with the flow meter**, enter the area, and ZoneFlow runs the valve for 10 minutes, reads the meter and sets the calibration. You get a message on your phone with the result.

The meter must measure **only this zone's water** while it runs. If it also counts other zones, the number will be too high.

---

## "The Area They Water": The Most Common Mix-Up

The area is where the water actually lands, not the size of the garden.

- **Drippers at each plant**: add up the wet circles. Ten tomato plants with a 30 cm wet patch each is only about 0.7 m², not the whole bed.
- **Sprinklers and soaker hoses**: the area they cover.
- **Not sure?** Run a service run, dig a few centimetres down and see how wide the wet patch is.

A wrong area is the most common reason a calibration feels wrong. Too big an area makes ZoneFlow think the system is weaker than it is.

---

## Zone Flow: Litres, Not Depth

ZoneFlow can also show how many **litres** each zone uses: the last watering, the last 30 days and the year so far. For that it needs a second number, **Zone Flow**: how many litres per minute the whole valve gives.

- Method 1 and Method 2 above set it for you automatically.
- Or enter it yourself: **Configure → Zone flow**: the number of heads and the flow of one head (drippers are usually given per hour, sprinklers per minute).
- With a flow meter, ZoneFlow uses the meter's real litres instead.

Zone Flow is only used to show litres. It never changes when or how long a zone waters. Leave it at 0 if you do not need litres.

---

## Calibrating the Rain Gauge

Only needed if your rain gauge is a **tipping bucket** that counts tips.

Each tip of the bucket is a small amount of rain, usually **0.2 mm** or **0.3 mm** (some are 0.254 mm, a hundredth of an inch). Find the number in the gauge's manual, or catch it yourself: slowly pour a known amount of water through the gauge and count the tips. Set it on the zone's device page as **Rain Gauge mm per Tip**.

If your weather station already reports a rain total (Ecowitt, Ambient Weather, Davis and others), you do not need this: choose **Rain total** as the sensor type instead. See the rain gauge guide.

---

## Drippers of Different Sizes on One Valve

ZoneFlow can only use **one** number per valve. If the heads on a valve are different (some strong, some weak), the calibration is the **average**. Plants on the weaker heads get less water than the number says.

For the most accurate result, put each type of emitter on its own valve (its own zone).

---

## How To Check That It Is Right

1. Water a zone and look at **Last Water Delivered**: the depth ZoneFlow believes it put on.
2. Dig a few centimetres down a few hours later. The soil should be damp to about the depth the plant's roots reach, not soaked and not dry.
3. Too wet? The real flow is higher than the calibration. Too dry? It is lower. Repeat Method 2 to fix it.

---

## When To Calibrate Again

- When you change emitters, add or remove heads, or change the pump.
- When the pressure changes (a new filter, a longer line).
- Once a year, or when plants look different from what ZoneFlow reports. Drippers clog slowly, so a yearly check is cheap insurance.

---

## Quick Answers

**Which number do I really need?** Only the **flow rate calibration**. Zone Flow (litres) is optional, and the rain gauge number only matters for a tipping bucket.

**Metric or imperial?** Either. ZoneFlow follows your Home Assistant units (or the zone's own units option) and converts for you.

**I changed it, will my past waterings change?** No. They stay as they were recorded. The new number applies from the next watering.

**It says the result is out of range.** Check the numbers: usually the area is too small (or too big) or litres and minutes are mixed up. The calibration has to be between 0.05 and 2 mm per minute.

**Does it matter for a lawn with sprinklers?** Yes, the same way. A simple way to measure it: put a few flat-bottomed cups spread over the lawn, run the zone for 15 minutes, and measure the average depth of water in the cups in millimetres. Divide by 15 and you have the millimetres per minute. Set it with the **Emitter Flow Rate Calibration** slider on the zone's device page.
