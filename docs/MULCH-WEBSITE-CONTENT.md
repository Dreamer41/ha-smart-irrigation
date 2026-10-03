# Website Content: Mulch Adjustment (Plain Language)

**Purpose**: Copy for your CloudFlare website explaining the mulch feature. Written to drive user engagement and explain why they should use it.

---

## Headline

### Bare Soil Dries Faster — Now You Can Account For It

ZoneFlow 1.5.1 adds Mulch Adjustment, so you don't have to guess how much more water bare soil needs.

---

## Short Explanation (Elevator Pitch)

If your garden has bare soil between plants, or young trees without a full canopy, water evaporates from the soil faster than from mulched or shaded ground. ZoneFlow 1.5.1 makes it easy to adjust for this without complicated calculations—just toggle the **Mulch** setting and dial the slider based on what you observe.

---

## Why This Matters

### The Problem

Irrigation schedules are based on reference evapotranspiration (ET), which is calculated for a well-watered reference crop—basically, a lawn or dense vegetation. But bare soil loses water differently. Here's why:

- **Bare soil**: Water sits on the surface longer before soaking in, and 50–80% of it evaporates before roots can use it
- **Mulched or shaded soil**: Much of that direct evaporation is blocked by mulch, bark, leaves, or a canopy
- **Result**: If you apply a "lawn schedule" to bare soil without adjustment, you'll underwater—even though the ET calculation is correct

### The ZoneFlow Solution

Instead of hand-tuning crop coefficients or guessing, just use the **Mulch** select:
- Set it to **Mulched** if soil is covered (default; no change for existing zones)
- Set it to **Not Mulched** if bare soil is exposed
- Dial the **Mulch ET Adjustment** slider (-50% to +70%) to tell ZoneFlow how much more, or less, water to apply. Heavy clay or shaded soil that holds water can go below zero.

That's it. Rain still counts as rain (no adjustment there), and you can dial it in over a week or two by watching how dry your soil gets.

---

## Scenarios: When to Use It

### Use "Mulched" (Keep Default)
- Mulch, bark, or leaf litter covers the soil
- Dense tree canopy or shrub that shades its own root zone
- Lawn or closed-canopy vegetable bed
- Soil stays consistently moist, no signs of stress

### Use "Not Mulched" + Slider
- **Bare soil between plants** → 20–25%
- **Young trees or shrubs** without a full canopy → 15–25%
- **Wide spacing** between plants (for air flow) → 15–20%
- **Windy site** (evaporation is higher) → 25–35%
- **Exposed, compacted soil** → 30–40%

**Start at 20% and adjust based on what you see.** If soil dries out too fast, bump it up by 5–10%. If it stays too wet, dial it down. After a week or two, you'll have it dialed in perfectly.

---

## How It Works (Simple Version)

1. **Default**: "Mulched" = no extra watering (same as before)
2. **Switch to "Not Mulched"**: ZoneFlow scales your water target up by the slider %
3. **Example**: If your routine calls for 40mm/week and you set the slider to 25%, you'll get 50mm/week instead
4. **Rain**: Counts as 100% rain—no adjustment there

That's it. Everything else (growth ramp, deep soak, deficit mode) works the same.

---

## Real-World Examples

### Example 1: New Vegetable Garden (Bare Soil)
- Planting area, no mulch yet
- Slider: 25%
- You notice: soil stays moist, no wilting after 5 days
- Dial it down to 20% if it's staying too wet

### Example 2: Young Tree (No Canopy Yet)
- Single tree in open lawn, 2 years old
- Bare soil ring around the tree to avoid grass competition
- Slider: 20%
- After the canopy fills in (year 3), switch back to "Mulched"

### Example 3: Coastal/Windy Site
- Exposed soil, constant wind
- Normal bare-soil adjustment: 20%
- Add extra 5–10% for wind = 25–30%
- Observe and dial from there

### Example 4: Established Mulched Garden (No Adjustment Needed)
- Everything mulched or shaded
- Keep default: "Mulched" (0% adjustment)
- ZoneFlow waters exactly as it did before

---

## FAQ

### Doesn't this just mean I should add more mulch instead?
Yes, you could! But sometimes you can't (exposed clay, new construction, aesthetic preference, or just not ready yet). Mulch Adjustment is for the situation *as it is today*, without waiting for a solution to settle in. Plus, even with mulch, different soil types and climates need different amounts of adjustment—the slider lets you fine-tune.

### Will this change how my existing zone waters?
No. Default is "Mulched" (no adjustment), so zones you don't touch work exactly as before. Only turn on "Not Mulched" if bare soil is actually exposed.

### What about rain?
Rain is always credited at 100%. The adjustment only affects what the soil needs from irrigation. If it rains 15mm, that's 15mm off your water bill—no scaling, no guessing.

### Should I hand-tune the crop coefficient instead?
No—that's a different thing. Crop coefficient (Kc) is about the *plant type* (grass vs. trees vs. vegetables). Mulch Adjustment is about *soil cover* for that plant. Keep Kc at the published value for your plant; use Mulch Adjustment for soil cover. ZoneFlow handles the math.

### Can I change it later?
Yes. Dial the slider anytime—there's no penalty. ZoneFlow will use the new setting on the next watering decision. Your mulch selection also survives restarts, so you don't lose it if you power-cycle.

### Does it affect deep soak?
No. Deep soak has a different job—it penetrates to the full root zone, which is a physical depth thing, not an evaporation adjustment. Mulch Adjustment only affects routine (shallow, frequent) watering.

---

## Next Steps

1. **Update Home Assistant** to ZoneFlow 1.5.1
2. **Open your zone** on the device page (Settings → Home Assistant Devices → [Your Zone])
3. **Look for "Mulch"** (Configuration section)
4. **If you have bare soil**, switch to "Not Mulched"
5. **Dial the slider** based on the scenario table above
6. **Watch for one week**, then adjust if needed

That's it. The hardest part is deciding whether your soil is actually bare or not—and you already know that. 😊

---

## More Information

- **Full user guide**: [Mulch Adjustment detailed docs](./MULCH.md)
- **Release notes**: [1.5.1 Beta release notes](./1.5.1-BETA.md)
- **AI Setup Guide**: [AI_SETUP.md](../AI_SETUP.md) (§5: Crop Coefficient & Mulch)

---

## Marketing Tagline

> **Water bare soil better. Just dial it.**

or

> **Mulch Adjustment: Fine-tune your garden without guessing.**

or 

> **The slider that makes bare-soil watering actually work.**
