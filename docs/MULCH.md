# Mulch Adjustment (ZoneFlow 1.5.1+)

## What is the Mulch Adjustment?

ZoneFlow's water demand calculation is based on **reference evapotranspiration (ET₀)**, which represents water loss from a well-watered reference surface: a short grass crop with no water stress. The challenge is that bare soil loses significantly more water to direct evaporation than vegetated ground does.

If your zone has **bare soil between plants** or **recently planted saplings** without a canopy, applying bare-reference ET directly will **underestimate** how much water you need to apply to keep the soil moist at the roots. The water your emitters deliver sits on bare soil longer before soaking in, and more of it evaporates before the roots can use it.

The **Mulch adjustment** lets you scale up the routine watering demand to account for this loss, without modifying the underlying ET₀ or crop coefficient values.

## When to Use It

### Use **Mulched** (default) when:
- Bare soil is covered by mulch, bark, or leaf litter
- The plant has a dense canopy shading the ground
- You have a closed-canopy tree or shrub that naturally shades its own root zone
- You have densely planted vegetables or a lawn with good ground cover

### Use **Not Mulched** when:
- Bare soil is exposed between plants
- You have young trees or shrubs without a full canopy yet
- You have wide spacing between plants to allow air flow
- The soil surface is clay, compacted, or has a crust that slows infiltration

## How It Works

When **Mulch** is set to "Not Mulched", ZoneFlow scales your weekly water target by the **Mulch ET Adjustment** percentage (-50% to +70%, default 20%): positive for soil that dries fast, negative for soil that holds water well. This applies equally under both demand models (interval-based and ET curve).

### Example:
If your routine weekly target is 40 mm and Mulch ET Adjustment is 20%, the actual target becomes:
- 40 mm × 1.20 = **48 mm per week**

The rain credit is calculated **independently** and is not affected by the mulch adjustment. If it rains 15 mm, that full 15 mm still counts toward your baseline demand—only the soil's evaporative loss is scaled up.

## Tuning the Slider

The **Mulch ET Adjustment** slider (-50% to +70%) lets you dial in exactly how much adjustment your situation needs.

### Recommended starting points:

| Situation | Suggested % |
|-----------|-------------|
| Lawn with good ground cover | 0% (stay "Mulched") |
| Heavy clay in shade | -20% to -30% |
| Dense clay, low evaporation | -10% to -20% |
| Windy site with exposed soil | 5–10% |
| Young trees, spacing between plants | 15–25% |
| Shrubs or mature trees without mulch | 10–15% |
| Bare soil, newly planted area | 25–35% |
| Very dry climate, sandy soil, exposed | 40–50% |

**Best practice**: Start at 20% and observe the first week or two. If the soil looks dry before the next cycle, increase by 5–10%. If it stays too wet, decrease by 5%. Keep notes of your observations so you can dial it in.

### Negative adjustments

Some soil holds water well enough that the standard demand would overwater it: heavy clay, shaded courtyards, areas with high humidity or frequent rain. Set **Not Mulched** and move the slider below zero. Example: -25% turns a 40 mm weekly target into 30 mm.

Large negative adjustments significantly reduce the calculated watering amount. Use them only if local conditions or observed soil moisture justify it. Start with -10% to -20%, watch the soil for a week or two, and move back toward zero if it dries out too fast. On sandy soil a negative value would underwater.

## Technical Details

- **Only affects routine irrigation**, not deep soak. Deep soak's job is root-zone penetration depth (a physical property), not surface evaporation loss.
- **Works with both demand models**: interval-based ("routine watering every N days") and ET curve ("routine watering when ET₀ reaches X mm/day").
- **Composes with other scalars**: growth ramp and deficit mode both affect routine demand. Mulch adjustment is applied after these, so they all work together naturally.
- **Independent of rain**: rainfall is always credited at 100%, then subtracted from the scaled demand. Mulch adjustment only affects what plants need, not what nature provides.

## Persistence

Your Mulch selection and Mulch ET Adjustment percentage are saved to Home Assistant's state storage and survive restarts and updates.

## More Information

See the [AI Setup Guide](../AI_SETUP.md) §5 (Crop Coefficient) for guidance on setting crop coefficients correctly, and why you should **not** try to hand-adjust Kc for mulch—that's what this adjustment is for.
