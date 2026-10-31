# ZoneFlow Changelog

All notable changes to this project are documented here.

For detailed release notes and upgrade instructions, see the **docs/** folder for each version.

## [Unreleased]

### Added

- **More rain restarts the dry-down.** New setting **Dry-Down Restarts After More Rain** (Rain group, 10 mm to start with, 0 turns it off). While a dry-down is on, if at least that much rain falls within any 24 hours, it starts over from that moment, so watering waits for the soil to dry again. Before, only a new crossing of the heavy-rain thresholds restarted it, so 10 mm more on top of an earlier storm changed nothing. After a restart the count starts again from zero, and a hand edit of Last Significant Rain is honored: rain before the edit is not counted. It restarts quietly: no alert, and the Status and Why? show the new end. Copied with Copy settings and presets; shown in inches with imperial units; translated into every language.

## [1.7.8] — Rolling rain credit for zones updated from 1.7.6, HACS downloads

### Fixed

- **A rain mark saved by 1.7.6 now rolls at once.** After updating to 1.7.7 a zone that already carried a rain mark kept the old way until that mark ended, so the rain credit read 0.0 mm and "if it watered now" showed a full dose in the middle of a wet spell. Such a mark is now adopted into the rolling credit the first time it is read: the days of rain before it count again, less the one dose it took.

## [1.7.7] — A plainer card, and a rain credit that rolls

### Added

- **A plain sentence on the garden overview.** Above the chips the overview now says in words how the garden is: "Your garden is doing well.", "Watering now: Chilis", "Chilis: needs a look" (amber), "Nothing needs water right now. Rain and soil have it covered." or "Watering is paused." It only restates what the zones' statuses already say; nothing is decided differently.
- **Recent activity on the zone card.** A new button opens a list of what the zone ran, skipped and stopped in the last 10 days, with the reason and the time of each ("Routine skipped at 05:30: recent rain (4.2 mm) covers the 13 mm needed"). It reads Home Assistant's own history of the zone's status, so nothing new is stored and it goes back as far as your history is kept.
- **Show details on the zone card.** The technical numbers of the Now section (litres of the last cycle, the weekly target, the 3-day peak temperature, water used over 30 days and the year, the growth ramp) now sit behind a "Show details" press, so the card starts with the valve, the next watering, the soil and the rain. Nothing was removed.
- **Status shows both the next routine and the next deep soak.** The status sentence names the next routine watering and the next deep soak, and the status sensor gets two new attributes, `next_routine` and `next_deep_soak`.
- **Drying out after rain stays visible.** While the drying hold lasts, the status sentence keeps saying so, with when watering resumes, beside later decisions (such as "rain counted as a watering") instead of being replaced by them.
- **Why? shows rain that already counted.** When rain counted as a watering, the rain line says how much rain was counted and how much of it that watering already used up.

### Fixed

- **The rain credit rolls.** Rain that counted as a watering takes one dose off the credit but no longer wipes the days of rain before it: the window keeps starting at the last real watering, a dose leaves with its day, and a real watering starts the credit over. Days of heavy rain no longer show as "full amount needed" the moment rain is counted. The credit and the watering amount share one calculation, so after heavy rain the zone skips more. A zone already carrying a mark from 1.7.6 keeps the old way until that mark ends.
- **Rain-counted deep soaks count at most once per calendar day**, so a second rainy hour the same day does not move the next deep soak again.
- **Two Polish card texts had Russian words in them** ("Wszystko wygląda w porządku" and "Widok prosty").

## [1.7.6] — Look up your plant, crop factors, Rain Ignored Below

### Added

- **All the new texts are translated** into every language ZoneFlow has.
- **Watering tips: what your plant usually wants per week.** A new button on the zone card (administrators) looks your plant up in the [Plant Variety Database](https://github.com/bripatch/plant-variety-database) (Wind River Greens, CC BY 4.0) and shows its usual weekly amount in your units. A kind of plant (pepper, basil, rose) gives the middle of all its varieties first. **Apply** sets the normal week to the middle of the range and moves the hot and cool weeks in proportion; nothing changes until you press it. Plants whose entry only has words (no weekly amount) are shown without an Apply. Only the weekly amounts are bundled (about 300 KB, read when you open the popup), with credit in the README and on the popup.
- **Look up your plant when you set up a zone.** The first setup screen (and the screen for a crop in a greenhouse) has an optional "Look up your plant" field. It is a list that filters as you type, each plant with its usual weekly amount in your units (the middle of a whole kind first, such as all cucumbers, then single varieties). Pick one and that amount becomes the zone's starting weekly targets right there (the hot and cool weeks keep their proportion to the normal one). Text that is not in the list is searched for on a second screen. The list comes before What's planted, which stays the fallback for a plant that is not in it; a pick also chooses the plant type that fits (deep soak, growth ramp) when What's planted is left on Something else, and a type you choose yourself is kept. Left empty, nothing changes and no screen is added.
- **The lookup also gives the crop factor (Kc), from FAO paper 56.** Crop coefficients typed in from Table 12 of Allen, Pereira, Raes and Smith (1998) (48 crops: vegetables, berries, fruit and nut trees, turf) are shown next to the weekly amount, in Watering tips and in the setup list, and **Apply** (or picking the plant at setup) sets the Crop Factor setting. Crops the plant database has no weekly amount for, such as avocado, olive, citrus and potato, can be picked for their crop factor alone. Credit is in the README, in `data/ATTRIBUTION.md` and on the popup.
- **Gaps in the lookup are filled, and every value says how sure it is.** Mango, guava (UF/IFAS), papaya and basil (published studies) have their own crop factors. A plant with nothing of its own gets an **estimated** crop factor from its water-use class (low, moderate, high), as landscape plant factors do (WUCOLS, MWELO, UC ANR), and a plant with a crop factor but no weekly amount gets one **worked out** from it (1 inch a week at a crop factor of 1.0). 1,747 of the 1,889 plants now have a weekly amount; only those kept in pots or trays (succulents, houseplants, microgreens) have none. Estimates are marked "about" or "(estimate)" in the card and the setup list, with their sources credited. The setup list shows only measured amounts and the crops; the rest is found by typing.
- **Rain Ignored Below (per day) is a setting.** A day's rain up to 3 mm has always counted as nothing toward the watering (a little drizzle only wets the surface). That 3 mm was fixed; it is now a slider in the Rain group, 0 to 5 mm in steps of 0.5, starting at 3 mm so nothing changes until you move it. Lower it for shallow roots or sandy soil so light rain counts too (it then ramps up to the Light share at 5 mm); the three Rain Efficiency sliders still decide how much of the larger rain counts. Copied with Copy settings and presets.

## [1.7.5] — The loader moves inside the integration, rain credit fix

### Changed

- **Nothing is written into your `/config/www` folder any more.** The small loader that lets the cards show on a dashboard opened while Home Assistant is still starting now ships inside the integration and is served from `/zoneflow_static/zoneflow-loader.js`, next to the card. At the first start after updating, ZoneFlow moves its dashboard resource to that address and deletes the old `www/zoneflow/zoneflow-loader.js` it wrote (the folder only when nothing else is in it). YAML-mode dashboards: change the resource URL to `/zoneflow_static/zoneflow-loader.js` (docs/GUIDE.md).

### Fixed

- **Rain after a "watered by rain" mark was wiped out by the old rain's credit.** When heavy rain counted as a watering, the amount used was taken off all the rain of the next days, even rain that fell after the mark and could never have been part of it. A zone marked by 23 mm and 19 mm days kept showing "Rain credit since the last watering: 0.0 mm" for five days while it rained again, and Why? and the next watering gave the full dose. The amount is now taken off only the rain of the mark's own day, which is the only rain it can have come from.
- **Last Water Volume and Water Used sensors were not created on Home Assistant 2025.1** (that version refuses a sensor that suggests a display unit without a unit converter). They are created again; newer versions were not affected.
- **A device switched by hand while a greenhouse evaluation was already waiting** could be switched back before ZoneFlow noticed the manual hold, on newer Home Assistant versions that hand state changes to listeners a moment later. The evaluation now lets pending state changes through first.

## [1.7.4] — Valve backup timer, help on every setting, fewer fixed values

### Added

- **Longest Valve Open Time, and the backup timer to set on the valve.** A new diagnostic sensor (zones with a valve), shown in the Safety group: the longest the valve is open in one go, worked out from the zone's own settings as they are now. It counts the biggest routine watering the zone can start (its weekly targets, the days between waterings in each temperature tier, the flow rate and the Routine Max Safety Runtime Cap), split the way the zone splits it (the Routine Pulse Count, more pulses where the soil or slope needs them), the deep soak the same way, and the service and check runs (Service Mode auto-off, the 15-minute button, a flow measurement). It follows every one of those settings at once. The sensor's attributes give the recommended timer: the longest plus the larger of 10 minutes or 20 %, rounded up to 5 minutes. **Check my setup** says it in a line: set the valve's own auto-off timer (Shelly, Tasmota, ESPHome, the device's app) to at least that, as a backup in case Home Assistant stops while the valve is open. A typed Water now is the person's own choice and is given apart in the attributes (`with_water_now_minutes`).

- **When Soil Gets Wet During Watering, for zones with a soil probe.** A new choice in the Soil settings: **Finish the watering** (the start, exactly as before: the routine watering always gives its planned pulses) or **Stop at the wet level**: before each later pulse of a routine watering the probe is read, and once it shows the Soil Moisture Wet Threshold or more the rest is not given. The soak between pulses is what lets the water reach the probe. A watering stopped this way counts as the watering (the interval starts again, the valve minutes count toward the daily cap) and sends a phone message. A probe with no usable reading keeps watering, and a press of Run Routine Now is never cut short. Only the routine watering, not the deep soak.

- **Minimum pulse length is a setting** for the routine watering (1 minute to start with) and the deep soak (5 minutes to start with): **Routine Minimum Pulse Length** and **Deep Soak Minimum Pulse Length**, next to the pulse count and the soak. A dose too small for every pulse to reach the minimum runs fewer pulses. The Longest Valve Open Time follows them.
- **Self-tuning can be turned off, and its numbers are settings.** A **Self-Tuning** switch (on to start with, as it always was) and two sliders in the Rain group: **Self-Tuning Presses Needed** (3 to start with) and **Self-Tuning Step** (0.5 days to start with). With the switch off, early presses of Run Routine Now and Snooze presses never change the dry-down holdoff.
- **Weekly summary time and fertilizing reminder time are chosen at setup** (and under Configure): 18:00 and 09:00 to start with, the old fixed times, so nothing changes until you pick another. They are not on the card.

- **My Valve's Own Timer.** Type in the minutes you set as the auto-off timer on the valve or switch itself (0 = not set). ZoneFlow cannot read that timer, but Check my setup now compares it with the Longest Valve Open Time: a warning if it is shorter (with the minutes to set instead), a tick if it is enough, and the warning comes back by itself if you later change a pulse count, a gap or the flow rate so the longest time grows past it.
- **The next watering, previewed in Why?** A new line: "If it ran now: 42 min in 3 pulses of about 14 min, with 20 min of soak between them. The valve is open at most 14 min at once." (or "in one go", or "nothing, the rain already covers it"). It uses the zone's own plan, so it follows every slider at once.
- **Simpler Settings popup.** The zone card's Settings opens with the everyday settings (the flow rate, the three weekly targets and the days between waterings; Watering time is its own button) and **Show all settings** shows the rest. The choice is remembered in the browser. Nothing is removed.
- **A "?" on every setting.** Each setting in the Settings popup, and each group, has a help button that opens the matching page on the ZoneFlow website (zoneflowirrigation.com/docs), where the card's help used to open GitHub pages. Each Settings group has its own help page on the website, with every setting in it explained under its own heading: what it does, its starting value and how to pick yours. The Repairs "learn more" links, the dashboard card's documentation link and the integration's documentation link go to the website too.
- **A Check my setup warning can be ignored.** A warning that is wrong for your zone (for example "the flow rate is still the example value" when that really is your flow rate) has an **Ignore** button. It asks you to confirm first. An ignored warning moves to an **Ignored** list at the bottom with a **Show again** button, no longer counts toward the overall result, and for the example flow rate its Repairs notice goes away too. If the warning goes away (you calibrate) and later returns, it is a new warning. Only warnings can be ignored (not a valve that is down), and only by an administrator.
- **A valve test at the end of zone setup.** The last step offers to open the valve for about 2 seconds and says whether it answered and closed again ("The valve answered…", "did not answer", "did not report closed: check it now"). It can be skipped, and the zone is added whatever the result.

### Changed

- **The three Rain Efficiency sliders (light, moderate, heavy rain) are shown.** They were hidden for every zone as "fine-tuning", but how much rain reaches the roots differs between shallow and deep rooted plants. They are in the Rain group of the zone card's Settings (under Show all settings) and unhide by themselves on existing zones.
- **Deficit Mode Water goes down to 30 %** (it stopped at 50 %).
- **A watering fires on its day even when the last one took hours.** The last watering is stamped when it finishes, and a watering counts as due a few hours early (6 hours) so the next one still falls on the set day. A run that took longer than that (a long soak between many pulses on clay) used to push the next one a day late; the early margin now grows with how long the last run took, up to 20 hours.
- **Water now with minutes splits into pulses**, like the zone's own routine watering: the zone's Routine Pulse Count, more pulses where the soil or slope needs them to avoid runoff, and the soak between them (it can be stopped in the soak). It was one single pulse. It still counts in the water record and does not move the schedule; the cap and the daily cap still apply. The 10-minute button on a phone notification works the same way. Service runs (the 1 / 5 / 10 / 15 minute buttons and Service Mode) stay one pulse.

## [1.7.3] — Days between waterings, Watering time, Delete zone, Valve Overlap

### Added

- **Days between waterings are settings.** Two new sliders next to the weekly targets in the zone's settings: **Routine Days Between Waterings** (normal and cool weather, 4 to start with) and **Routine Days Between Waterings (Hot)** (3 to start with), 1 to 10 days each. These were fixed before. A longer gap gives a bigger dose each time, so the weekly target is still met; if one watering then no longer fits the zone's Routine Max Safety Runtime Cap, Check my setup says so. Copied with a zone's settings and presets.
- **Valve Overlap, for zones that share a pump.** A new setting (0 to 10 seconds, default 0 = as before) in the Safety group: when a zone finishes its last pulse and another zone is waiting for the same pump, the next zone's valve opens first and the finishing zone's closes the set number of seconds later, so the pump never pushes against shut valves and the pipes do not bang. Not used for service runs or flow measurements, or when both zones share one flow meter; the next zone skips its pump warm-up and the finishing zone its settle delay for that hand-over. Shown only where a pump is shared.
- **Watering time on the zone card.** A new **Watering time** button opens a small form: when the routine watering (and the deep soak, where it is on) starts, at a set clock time or before or after sunrise or sunset with an offset in minutes. Save changes it at once (the zone reloads). It is the same setting as Configure > Settings, one tap away. Also the service `zoneflow.set_schedule`.
- **Delete zone button.** At the bottom of the zone card's Settings popup (administrators only): *Delete this zone*, then a confirmation. The same removal as Delete on the device page. Also the service `zoneflow.delete_zone`, which only deletes the zone it names (never "the only zone"). Both new services (`set_schedule`, `delete_zone`) are for administrators; `set_schedule` refuses while the zone is watering.
- **The rain that starts the dry-down is a setting.** Three new sliders in the zone's settings (Rain group, next to Routine Dry-Down Holdoff): **Dry-Down Rain Threshold (24h)**, **(4 days)** and **(7 days)**. They start at 35, 50 and 100 mm, the values that were fixed before, so nothing changes until you move them. Rain over any of them starts both dry-down holdoffs (routine and deep soak). Shown in your units; hidden where no rain is measured; copied with a zone's settings and presets.

### Changed

- **One place works out the routine dose.** The routine watering, the hourly "watered by the rain" check and the Status estimate now share the same calculation, so they can never disagree about how much a routine watering gives. No change in behaviour.

## [1.7.2] — Watered by the rain, drag and drop plants

### Changed

- **The Status sentence says how much the next watering is expected to give**: "Next watering Mon 05:30, estimated 12 mm" (a routine watering: the dose the zone's settings call for, less the rain so far; a deep soak: its target). It is left out when there is nothing to estimate.
- **Next Irrigation Estimate is hidden** (it keeps working, and unhides under the entity's settings): Days Until Next Run says the same, and the Status says when. Automations and cards that use it are not affected.

### Added

- **Drag and drop plants between zones.** On the overview card, the **Move plants** button shows each zone's plants as chips; drag a chip onto another zone (mouse or finger) to move the plant there. Every drop asks first: where to, what becomes of a main plant already there (keep it, make it a record, archive it, or swap), and whether to use this plant's watering settings too (then every plant in that zone is watered that way). A zone with no valve takes the plant as a record only. The Move button in the Plants popup works as before.
- **Watered by the rain.** Once an hour a zone works out what its next routine watering would give, on its own settings. When the rain since the last watering is already more than that, the zone counts as watered: its interval starts again, the Status and Why? say so ("Routine watering counted as done at 14:00: the rain (19.8 mm) was more than the 14.0 mm it would give"), and the next run waits for its turn. Nothing runs and no litres are counted. Rain beyond the one dose is still credited to the next watering, and the same rain is never counted twice. A paused or busy zone is left alone.
- **Deep soak by the rain.** The same hourly check looks at the rain since the last deep soak (at most the last 24 hours). When it is more than the zone's deep soak target, or, spread over the last 72 hours, more than the target plus 5 mm, the deep soak counts as done (and as the routine watering, like a deep soak that ran); the Status says so.
- **Mark Deep Soak Done button**, for a zone that has no rain measuring (no rain gauge, no Weather Underground): press it when you saw enough rain fall or soaked the bed by hand. Hidden where rain is measured.

## [1.7.1] — Water now fix, quick setup and nursery plants

### Added

- **Quick setup for a new outdoor zone.** The first form has a *Quick setup* box (ticked): after the name, plant and place it asks only for the valve, how the water is delivered and how much it gives (number of emitters, flow of one, area wet; there is no default, as drip and sprinklers differ a lot), uses the sensors it clearly found, and takes the rest from the plant type and the default climate. Untick it for the full setup as before.
- **Nursery plants: ready to move.** Follow a plant towards the day it can go to its bed (the usual days for its type are suggested, you set the planting date). Its stage (seed, seedling, ready to move) shows in the Plants popup; a plant that is ready gets a badge on the zone card and its overview row, and one phone message. A plant you move becomes established. Services: `set_plant_ready`, and `ready_days` / `planted` on `add_plant`.

### Fixed

- **Water now / Run routine now waters even when the routine is not due.** The button used to do nothing, silently, before the next watering was due. It now runs the routine watering at once and counts it as done. Pause, snooze, frost, rain falling now and the runtime caps still apply.

## [1.7.0] — Areas, plants and easier setup

- **Changed (docs)**: the README is now a short introduction that points to the website and to the guides in `docs/`. The long README moved, unchanged, to [docs/GUIDE.md](docs/GUIDE.md). New [docs/CALIBRATION.md](docs/CALIBRATION.md): how to set the flow rate, Zone Flow (litres) and the rain gauge
- **New**: **areas**. An area is a part of the garden (*Backyard*, *Front yard*) that holds the sensors its zones share: the rain gauge (with its tip size), the outdoor temperature, the weather entity and the phone to notify. Add one from the add-integration menu (*Add an area*) or from a zone's **Configure -> Where is this?** (*New area* makes one from that zone's own sensors). A zone uses its area's sensors unless it has one of its own, and its card says so ("Uses its own rain gauge, not Backyard's"). Each area has its own **Pause** and **Snooze Today** (a second layer: a zone's own Pause stays as it is) and a **Water Used** total in litres. The zone's **Where is this?** dropdown (on its card, and in Configure) moves it between areas and greenhouses; the overview card and the generated dashboard group zones by area. Zones with no area work as before
- **Changed**: a **deep soak that comes due soon after a routine watering now waits for the next routine slot and replaces that routine**, instead of watering again the next day. It waits at most one routine interval (3 or 4 days) past its due date. A manual *Run Deep Soak Now* still runs at once, and a zone that has never done a deep soak is not affected
- **New**: **plants with a history**. Each zone with a valve gets a main plant (made for you on update, nothing is lost); it keeps its live settings on the zone's own sliders as always. The zone card's **Plants** button lists the plants and each one's **History** (settings changed, fertilized, notes, moves), adds a plant, moves one to another zone (asking what becomes of the main plant already there: it stays as a record, is archived, swaps places, or the moved plant joins as a record only), makes a record the main plant, renames a plant, removes a plant (it stays on record) and writes notes. A moved plant, or one made the main plant, brings its own planting date, health and fertilizing; the bed keeps the way it is watered unless you ask for the plant's settings too. Also as services: `add_plant`, `move_plant`, `set_main_plant`, `remove_plant`, `rename_plant`, `add_plant_note`
- **New**: **copy settings and presets**. Give a zone another zone's watering settings (`copy_settings`), or save a zone's settings under a name (`save_preset`) and use them on any zone later; the Plants popup has the controls. Adding a new zone has a **Start from** choice: a copy of a zone or a preset. Valve, sensors, flow rate, rain gauge tip size, planting date and notes are never copied
- **New**: **Check my setup**, a plain checklist on the zone card (valve, rain gauge, temperature, forecast, flow rate, litres, soil probe, last watering, phone) with the problems first; **Calibrate the flow rate** on the card: run 15 minutes, enter the litres and the area, and the flow rate and Zone Flow are set (`calibrate_flow`)
- **New**: **Water now for N minutes** (a stepper on the card, `water_now`): safe (not while paused, never longer than the zone's runtime cap, inside the day's cap), counts in the water record, does not move the routine or deep soak schedule
- **New**: **Why?** under the zone's status shows the numbers behind the next watering; **My Garden** summary on the overview card (watering now, next, rain today, zones that need a look, water used); a **Simple view** option on the zone card (status and a few controls, the rest behind Advanced settings; on for newly added cards); a **?** beside settings that links to the guides
- **New**: **setup helpers**: the first setup screens list the rain gauges, thermometers, weather entities, phones and valves found in Home Assistant with their names and values and fill in a clear single match; a Step 2 of 4 counter; plainer questions (*Do you know your soil type? Skip if not*); and **Fix buttons in Repairs** for a phone that no longer exists, a sensor offline for days and a flow rate never set
- **New**: a **greenhouse and its crops are a group of their own** on the overview card and the generated dashboard, with **Pause** and **Snooze Today** for the whole greenhouse (its crops' watering; the climate control carries on).
- **New**: the zone card shows **how the zone is watered** (temperature tiers or ET) and, for a zone with more than one plant, **lists its plants**; the overview card has an **Add area** button; adding a zone asks **which area it is in** (when there are areas).
- **New**: **buttons on phone messages** (Home Assistant companion app): a watering cancelled for rain, an overdue zone and a fertilizing reminder carry *Water 10 min*, *Snooze today* and *Fertilized*; the overview card can **create a ZoneFlow dashboard** in one click
- **Fixed (tests)**: a test of Paused Until depended on the order three days of timers fired in

## [1.6.5] — Water use in litres and rain from weather stations

- **New**: **rain from weather stations**. A new setting, **Rain gauge sensor type** (Configure → Zone settings), tells ZoneFlow what the rain sensor reports: a **tip counter** (as before), a **rain total** in mm or inches (lifetime, daily or weekly, as from Ecowitt, Ambient Weather or Davis), a **rain rate** in mm/h, which is added up over time, or **rain per reading** (the amount since the previous update, as the Tempest *Precipitation* sensor reports it). Only the increase of a total counts, so a reset at midnight is not rain, and the tip size setting is hidden for totals and rates. Changing the sensor or the type starts the rain history again. New guide: [docs/RAIN-GAUGES.md](docs/RAIN-GAUGES.md)
- **New**: **water use in litres (gallons)**. A new **Zone Flow** setting (litres per minute the zone's valve gives) turns valve minutes into litres. Set it under **Configure → Zone flow** (heads x flow per head), or it is set when you work out or measure the flow rate. The zone card shows the **last watering as mm and litres** (new **Last Water Volume** sensor), and new **Water Used, Past 30 Days** and **Water Used This Year** sensors (calendar year, from 1 January) keep a daily record of about 400 days. A flow meter's measured litres are used when there is one. Estimates only, never used for watering decisions; zones without Zone Flow or a flow meter show mm only, and earlier watering stays in mm
- **Fixed**: **Rain Today** showed a sensor's whole history as rain today when rain tracking started on a sensor that already held a count (a new zone, a switched sensor, or a sensor that came online after startup)
- **Fixed**: a rain total that starts again every day or week could be taken for a sensor glitch on a heavy-rain day and under-count the rain

## [1.6.4] — Rain gauge fix, measure flow by volume

- **Fixed**: **rain amounts that were too high** on zones with a rain gauge. The rain windows keep cumulative millimetres (tips × mm per tip), so a calibration that differed from the one the samples were recorded with — the *Rain Gauge mm per Tip* slider moved, or a restart that read the default before the saved value was restored — added (all tips so far) × (the difference) on the next tip: about 4 mm of rain that never fell with 436 tips and 0.309 vs 0.300. The stored samples are now rescaled to the calibration in use. A wrong amount already recorded fades out of the 14-day window by itself
- **New**: **Configure → Flow rate: measure it by the litres a service run gave** — for zones without a flow meter. Press a Service Run button (15 min is the most accurate), catch or read the water (bucket, barrel, water meter), and enter the minutes, litres and wet area; ZoneFlow sets the Emitter Flow Rate Calibration. The result is the zone's **average**: ZoneFlow has one rate per zone, so for a precise result every emitter on a zone's valve should be the same type and flow. Put different emitters on separate valves (zones); the plants on the weaker emitters of a mixed zone get less than the average shown. The emitter-count option now says it assumes equal emitters
- **Fixed**: deleting the Weather Underground entry now switches "use Weather Underground" off in the zones that used it, so manual rain is offered again (before, those zones kept hiding it and rain read 0)
- **Changed**: the integration's `iot_class` is now `cloud_polling`, since Weather Underground calls a cloud service (optional)

## [1.6.3] — 15-minute service run

- **New**: a **Service Run 15 min** button next to the 1, 5 and 10 minute ones, for a longer flow-calibration test. Like the others it is never counted as watering and respects the daily safety cap

**Update your dashboard**: the zone card shows the new button by itself. A hand-made dashboard can add `button.<zone>_service_run_15_min`

## [1.6.2] — Stuck-probe protection, hardening and tidier greenhouse deletion

- **Fixed**: a soil-moisture probe stuck on "dry" (or reading dry because it is out of the soil) that keeps reporting made the zone water a **full** interval dose **every morning** — about four times the weekly target in a four-week simulation. A run a dry probe brings forward now gives only the share of the dose the days since the last watering call for (at least a quarter), so even a stuck probe stays near the weekly target

- **Fixed**: Weather Underground answering with something that isn't a report (a list, a string, NaN, infinity, a missing key) no longer raises an error in the answer parser or the station-picking form; NaN and negative totals are never counted as rain
- **Fixed**: a hand-entered rain amount that isn't a finite number is refused; a zone that names itself as its greenhouse is just a zone
- **Changed**: deleting a greenhouse zone now switches off its fans, misters and heater and closes its vents (nothing controls them any more); a reload or restart still leaves them alone
- **Translations**: the "nothing is on hold" message of Resume Automatic in every language

---

## [1.6.1] — Rain without a gauge, Resume Automatic and a ready-made dashboard

- **New**: **Weather Underground rain (experimental)** — an outdoor zone **without a rain gauge** can borrow rain from 1-3 private weather stations within 2 km (nearer is better). One shared entry for the whole Home Assistant (Add integration → ZoneFlow → Set up Weather Underground rain), the station readings combined (3 stations: the middle one, 2: the lower one, 1: as is), polled every 2 hours and every 10 minutes around a watering. Only for rain deduction, not 100 % reliable. Read [the guide](docs/WEATHER-UNDERGROUND.md) first: check the Weather Underground map for stations nearby, and note the free API key needs your own station uploading temperature and humidity. Not for zones with a rain gauge
- **New**: **manual rain** — enter rain read from a simple gauge (Manual Rain number + Add Manual Rain button, or the `zoneflow.add_rain` service), up to 14 days back; hidden on zones with a gauge or Weather Underground
- **New**: **Forecast Skip Hit Rate** sensor — each watering skipped for forecast rain is judged 48 hours later against the rain that really fell
- **New**: **Resume Automatic** button for greenhouse and indoor zones ends a manual hold at once
- **New**: **Auto Resume** switch and **Auto Resume After** (0.5-24 h) — a device you switched by hand goes back to automatic after that time, or waits for the button when the switch is off
- **Changed**: Auto Resume After replaces **Manual Hold Time**; your old value is carried over, rounded up to the next half hour ("0" becomes 0.5 h)
- **New**: a heater switched on by hand is taken back once the inside temperature goes above the vent temperature, whatever the hold setting
- **New**: **several crops in one greenhouse** — Add integration → ZoneFlow → *Add a crop to a greenhouse*: each crop has its own valve, soil probe, plant and schedule and uses the greenhouse's climate and inside sensors (read live). Crops are connected via their greenhouse in the device list, listed on the greenhouse's card, under it in the overview card, and on its tab in the auto-generated dashboard. Zones set up the old way join a greenhouse under Configure → Greenhouse. Deleting a greenhouse leaves its crops working on their own
- **Changed**: a greenhouse or indoor zone without climate devices no longer shows the Greenhouse Status sensor and Greenhouse Control switch
- **New**: **auto-generated dashboard** — `strategy: {type: custom:zoneflow}` builds an overview tab and one tab per zone
- **Changed**: adding a second zone now starts with a small menu (Add a zone / Set up Weather Underground rain)
- **Fixed**: a test of two zones sharing a pump was timing-dependent on Windows
- **Tests**: full suite passes

See [docs/1.6.1-RELEASE-NOTES.md](docs/1.6.1-RELEASE-NOTES.md) for details and upgrade instructions.

---

## [1.6.0] — Greenhouse & indoor climate control

- **New**: zone types — **outdoor** (as before), **greenhouse** and **indoor**. Existing zones stay outdoor; nothing changes for them. Change the type any time under Configure → Zone type, nothing is deleted
- **New**: climate control for greenhouse and indoor zones — **fans, vents (covers or switches), misters and a heater**, any number of each, from `switch`, `input_boolean`, `fan`, `cover`, `valve` and `climate` entities, driven by an inside temperature sensor and optional humidity, light and outside temperature sensors
- **New**: the valve is optional — a **climate-only zone** has no watering at all, and its watering settings, sensors, buttons and Repairs issues are hidden
- **New**: outside-air check — vents and fans only open when the outside air is cooler than inside, so a hot afternoon never gets hotter air
- **New**: misting by temperature, humidity or light, in short pulses with hard limits: confirmed off, one retry, then it halts until Reset Irrigation Lock, stuck-mister watchdog, Max Misting Per Hour, no misting at night / when cold / while heating / in frost
- **New**: failsafes — if the inside sensor fails (unavailable, or silent for **Sensor Offline After**, 4 hours by default), misters go off, vents and fans follow **Sensor Failsafe**, and the heater follows **Heater Failsafe** (off, part of the time, or part of the time while cold outside; 10 minutes on in every 20). While that heater may run in the cold, the vents stay shut
- **New**: every device command has a time limit, so a device that never answers can't stall the climate control
- **New**: **backup inside temperature sensors** — control carries on with the first working one, and you are told if main and backup disagree by more than 5 °C for 30 minutes
- **New**: Manual Hold — a device you switch yourself (in Home Assistant, with a wall button or the device's own app) or another automation switches is left alone for a set time; a device coming back from unavailable is not mistaken for you
- **New**: changing **Vent Open Position** moves vents that are already open; an outdoor zone changed to a greenhouse starts from its climate's temperatures
- **New**: turning **Greenhouse Control** off switches off a heater ZoneFlow had switched on
- **New**: Greenhouse Status, Inside VPD, Misting Today and Ventilation Allowed sensors, the Greenhouse Control switch, and about 20 climate settings that appear only when the hardware they act on is set up
- **New**: add or change sensors, backup sensors and devices later under Configure → Valve, sensors and climate devices — no re-setup
- **New**: the ZoneFlow card and overview card show climate zones (status, climate settings groups, greenhouse icon for valveless zones)
- **New**: all the new texts translated into the 19 languages (machine translated; corrections from native speakers welcome)
- **Docs**: new [Greenhouse and indoor zones guide](docs/GREENHOUSE.md); [AI_SETUP.md](AI_SETUP.md) gets a greenhouse and indoor section (§7.11) and updated questions and flow; README updated. If you have a heater, the guide recommends a hardware frost thermostat and a backup temperature sensor placed away from the main one
- **Fixed**: a climate-only zone no longer gets the irrigation "flow rate is still the default" Repairs warning
- **Tests**: full suite passes — 650 tests; climate engine also exercised on a sandbox Home Assistant (hot, outside-air check, cold, sensor loss and recovery, misting)

---

## [1.5.1] — Mulch Adjustment, Mark Watered & card fixes

- **New**: Mark Watered button — record a manual watering (hose, can); the routine clock restarts and the next run doesn't water again
- **New**: Zone card buttons (Water now, Deep soak now, Snooze, Fertilized, Service runs) act on one tap, with no "more info" popup to press again
- **New**: Hover tips on key settings in the card (English; more languages to follow)
- **Changed**: Finnish card wording for Water now / Deep soak now / Snooze / Fertilized

- **New**: Mulch adjustment for routine irrigation (select + slider) — account for bare-soil evaporation without hand-tuning Kc
- **New**: Mulch ET Adjustment slider (-50% to +70%, default 20%): up for exposed soil, down for water-holding soil such as heavy clay or shade
- **Fixed**: Home Assistant 2025.1+ background task compatibility (time-change listener race condition in test)
- **Docs**: New [Mulch feature guide](docs/MULCH.md), updated [AI_SETUP.md](AI_SETUP.md) climate adjustment section
- **Tests**: Full suite passes on HA 2024.3.3 (Py 3.11) and HA 2025.1.4 (Py 3.12) — 535 tests, zero regressions

See [docs/1.5.1-BETA.md](docs/1.5.1-BETA.md) for full details and upgrade instructions.

---

## [1.5.0] — Easier to Use

**Released**: 2026-09-14

- **Built-in ZoneFlow dashboard card** — add per zone, it finds entities automatically, shows only what the zone uses
- **ZoneFlow overview card** — every zone in one table: status, next/last watering, sorted by name or next watering
- **Status sensor** — one sentence per zone (watering now, what it decided today, or when it waters next)
- **Device page redesign** — Configuration & Diagnostic sections, cleaner layout, Download diagnostics button
- **Pause switch** & **Paused Until** date — stop watering temporarily
- **Frost guard** — hourly re-checks, uses temperature sensor or weather entity
- **Notifications** — per zone (all/warnings/none), weekly summary per phone
- **Repairs** — auto-detect: valve unavailable, sensor offline, missing notify target, uncalibrated flow
- **Plant presets** at setup, **flow-rate helper** from emitters or flow-meter measurement
- **Languages**: German, Dutch, French, Spanish, Italian, Finnish, Swedish, Polish, Portuguese (regional variants + Czech, Danish, Hungarian, Norwegian, Russian, Slovak, Ukrainian, Simplified Chinese)

---

## [1.4.3] — Service Mode & Deep Soak Integration

**Released**: 2026-08-20

- **Service Run buttons** — 1/5/10 min test watering
- **Service Mode switch** — keep valve open until switched off, auto-shutoff after 30 min with phone alert
- **Deep soak integration** — a completed deep soak counts as the routine watering; routine interval restarts from it

---

## [1.4.2] — Rain Efficiency & Deficit Mode

**Released**: 2026-07-15

- **Rain Efficiency** — what % of rainfall actually reaches the roots (depends on soil, drainage, slope)
- **Deficit Mode** — reduce watering during dry spells to encourage deep rooting
- **Split-cycle pulses** — for clay soils and slow drainage

---

## [1.4.1] — Deep Soak

**Released**: 2026-06-10

- **Deep soak cycle** — periodic deeper watering (1–2 weeks) to wet the full root zone
- **Configurable soak interval and target depth**
- **Hourly rechecks** — don't soak if rain recently fell

---

## [1.4.0] — Demand Models

**Released**: 2026-05-01

- **Interval-based demand model** — "water every N days" (simple, predictable)
- **ET curve demand model** — "water when ET₀ reaches X mm/day" (responds to weather, more efficient)
- **Switch between models** without losing configuration

---

## [1.3.0] — Scheduling & Forecast

**Released**: 2026-03-15

- **Routine irrigation schedule** — configurable time of day
- **Deep soak schedule** — separate time, independent of routine
- **Weather forecast gate** — skip watering if rain is forecast
- **Rain counter** — integrated rain measurement

---

## [1.2.0] — Soil & Site Configuration

**Released**: 2026-02-01

- **Soil type** — sandy, loam, clay (informational; drives recommended split-cycle, rain efficiency)
- **Drainage** — fast, medium, slow (informs deep-soak interval)
- **Slope** — flat, slight, moderate, steep (affects water runoff, infiltration)
- **Irrigation method** — drip, micro-sprinkler, sprinkler, soaker, other (determines emitter efficiency defaults)

---

## [1.1.0] — Foundation & Growth Ramp

**Released**: 2026-01-10

- **Growth ramp** — automatically scale back watering for young plants, ramp up as canopy fills
- **Crop coefficient (Kc)** — per-plant ET₀ adjustment
- **Hot/Cool/Normal temperature tiers** — respond to ambient heat
- **Pump safety** — cumulative runtime cap per day to prevent pump stress

---

## [1.0.0] — Initial Release

**Released**: 2025-12-15

- **ET₀-based irrigation scheduling** — Hargreaves-Samani reference evapotranspiration
- **Zone-by-zone scheduling** — independent for each valve
- **Flow rate & valve control** — pulse-count or timed cycles
- **Home Assistant integration** — entities for every parameter, automatable via services
- **CSV logging** — water used, rain, ET₀, decisions (for analysis & debugging)

---

## Versioning

ZoneFlow follows [Semantic Versioning](https://semver.org/):
- **MAJOR** (X.0.0): Breaking changes to dashboard/configuration or major new features
- **MINOR** (X.Y.0): New features, non-breaking changes
- **PATCH** (X.Y.Z): Bug fixes, documentation, translations

---

## How to Report Issues

If you find a bug or have a feature request:
1. Search [existing issues](https://github.com/haenv/ha-smart-irrigation/issues) first
2. If it's new, open an issue with:
   - Your HA version and Python version
   - Reproduction steps (if it's a bug)
   - Expected vs. actual behavior
   - Relevant logs or screenshots
3. Feature requests: describe the use case and why it matters

---

## Contributing

Contributions are welcome! See the repository's CONTRIBUTING.md (if present) or open an issue to discuss before starting major work.
