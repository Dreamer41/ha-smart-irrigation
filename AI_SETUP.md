# ZoneFlow — AI Setup Guide

> **If you are an AI assistant reading this file because a person asked you
> to help them set up ZoneFlow: this whole file is written for you.** Follow
> it top to bottom. The person should not need to open any other doc in this
> repo, and you should not need to ask them anything not listed here.
>
> Drive the conversation. Ask one question (or one small group of related
> questions) at a time, use sensible defaults instead of asking about every
> field, and get the integration actually configured and running a test
> pulse before you consider the job done. Do not explain ZoneFlow's internal
> architecture unless asked — the person wants working irrigation, not a
> code tour.

> **Non-negotiable, before anything else below:**
> - Never guess an entity ID — confirm it with the person or a real tool
>   lookup before submitting it.
> - Never disable, bypass, or suggest a workaround for a safety watchdog
>   (stuck-valve force-off, power-loss abort, stale-lock recovery). Not
>   configurable by design.
> - Never edit `calculations.py` or any other integration source file as
>   part of "setup" — this is entity selection + number tuning through the
>   UI only, never a code change.
> - If something doesn't fit this guide, say so plainly and point the
>   person at opening a GitHub issue rather than improvising.
>
> (Full detail on each of these is in §9 at the end — read this block now,
> that section later.)

## 0. What you're setting up, in one paragraph

ZoneFlow is a Home Assistant custom integration for drip/valve irrigation.
Each **zone** (one plant, bed, or lawn area with its own valve) is added as
its own separate config entry, done through Home Assistant's normal "Add
Integration" UI flow — there is no YAML to write. Your job is to (a) work
out what to put in each field of that flow and each crop-relevant tunable
number, and (b) either enter it yourself (if you have tool access to their
Home Assistant — §1a) or tell the person exactly what to click and type
(if you don't — §1).

## 1. First question: who's doing the clicking?

Before anything else, work out — and if it's not already obvious from how
you were invoked, just ask the person outright — which mode this is:

- **Mode A — you drive it directly.** You have live tool/API access to the
  person's actual Home Assistant instance (an MCP server, a long-lived
  access token you can call the REST API with, or equivalent). If so, tell
  the person you can configure this for them directly and just confirm
  before each real change (creating the config entry, setting number
  values) — you don't need to walk them through clicking anything. See
  §1a for the concrete calls.
- **Mode B — you guide, they click.** You have no tool access, only the
  chat. Say so, and be an efficient guide: tell them exactly what to click
  and type, one screen at a time, and ask them to paste back what they see
  (entity lists, error messages, confirmation screens) so you can keep
  steering without them needing to describe HA's UI to you from scratch.

If you *do* have HA tool access, still ask the person once, up front,
whether they'd rather you just do it or walk them through it themselves —
some people want to watch/learn the UI, most want it just done. Respect
whichever they pick.

**Also ask now** whether they'd like a ready-to-paste dashboard card for
this zone once setup's done (§8 — purely cosmetic, entirely optional).
Asking here, not at the end, matters: if they say yes, you note this zone's
entity IDs as you naturally encounter them while walking through §4 and §4a
below, instead of having to go back and rediscover them from scratch after
everything's already set up. If they say no, skip §8 entirely and don't
bring it up again unless they ask.

Either way, the information you need to gather is the same — §2 through §7
below. Only the *mechanism* for entering it differs.

### 1a. Mode A mechanics: driving the config flow via the REST API

If your tool access is via Home Assistant's REST API (directly, or through
an MCP server that exposes raw HTTP), a config entry is created by starting
and stepping through a **config flow**, the same state machine the UI form
walks — there is no "just POST the final data" shortcut, because
`config_flow.py` is a two-step flow (zone name, then entities/schedule):

1. `POST /api/config/config_entries/flow` with body
   `{"handler": "zoneflow", "show_advanced_options": false}`. The response
   includes a `flow_id` and the first form's `data_schema` (the zone-name
   step).
2. `POST /api/config/config_entries/flow/<flow_id>` with body
   `{"zone_name": "<the name you agreed on>"}`. The response is the second
   step's form — read its `data_schema` to confirm you're matching field
   names/types exactly (don't hardcode them from this doc if the schema
   response disagrees; the live response is ground truth).
3. `POST /api/config/config_entries/flow/<flow_id>` again with the full
   entities/schedule payload (all the fields from §4's table, keyed exactly
   as the schema names them). A successful response has `"type": "create_entry"`
   and includes the new `result` (the config entry). An error response
   has `"type": "form"` again with an `errors` object — fix and resubmit,
   don't guess blindly at what changed.
4. Once created, the zone's `number.*` entities exist with factory
   defaults. To set one from §5's table, call the `number.set_value`
   service: `POST /api/services/number/set_value` with
   `{"entity_id": "number.<zone>_<field>", "value": <float>}`. Confirm
   afterwards by reading the entity's state back
   (`GET /api/states/<entity_id>`) rather than assuming the call worked.
5. To run the verification pulse from §7: `POST /api/services/zoneflow/test_pulse`
   with `{"entity_id": "<any entity belonging to that zone's device>", "seconds": 10}`
   (or however your tool's service-call helper targets a specific config
   entry/device — some MCP servers want a device_id instead of an
   entity_id; check your tool's own parameters rather than assuming this
   shape). Then read back the valve and pump-power states to confirm the
   pulse actually happened.

If your tool access is a higher-level MCP for Home Assistant rather than
raw REST, look for whatever it calls "start config flow" / "add
integration" / "call service" — the sequence above is the same regardless
of which concrete tool call performs each step.

Whichever way you're driving it, **never silently create the entry or
change a number value without having told the person what you're about to
set it to** — a quick "I'm going to set X to Y because Z, creating the zone
now" is enough; you don't need to wait for a reply on every single field
once they've agreed to let you drive.

## 2. Prerequisites (check these first, in order)

1. **The custom component files are installed.** They should already be at
   `/config/custom_components/zoneflow/` on the person's Home Assistant. If
   you have file access and they aren't there, that's step zero — get the
   contents of this repo's `custom_components/zoneflow/` folder onto their
   system first (HACS custom repository, or copying the folder manually),
   then have them restart Home Assistant. If you have no file/HA access at
   all, just tell them this prerequisite plainly and ask them to confirm
   it's done before continuing.
2. **They have already restarted Home Assistant** after installing (custom
   integrations require a full restart the first time — a UI reload is not
   enough).
3. Ask them, in one message, for the physical setup of the **first zone**
   they want to configure:
   - What are they watering (a plant/crop name, or "lawn")? You'll use this
     later for §6's default suggestions and it becomes the zone's display
     name.
   - Do they already have Home Assistant entities for: a valve (switch), a
     pump power sensor, a rain gauge tip counter, and an outdoor temperature
     sensor? If any don't exist yet, that's a hardware/other-integration
     problem outside ZoneFlow's scope — tell them plainly and stop for that
     piece; don't invent a workaround.

## 3. Find the entity IDs

If you have HA tool/API access, search for candidates and propose them
rather than asking the person to hunt for IDs blind:

- Valve: a `switch.*` entity that plausibly controls water flow (name
  hints: "valve", "water", "irrigation", "zone", the crop name they gave
  you).
- Pump power: a `sensor.*` entity reporting watts (name hints: "pump",
  "power"). This is used to confirm the pump is actually drawing current
  during a pulse, not to control the pump.
- Rain counter: a `counter.*` or `sensor.*` entity that only increases
  (a tipping-bucket rain gauge's raw tip count, or a cumulative mm sensor).
- Outdoor temperature: a `sensor.*` with device class `temperature`.
- (Optional) Notify target: a `notify.*` entity for phone alerts.
- (Optional) Weather: a `weather.*` entity, for the forecast gate (§6).

Present your best-guess matches and ask the person to confirm or correct
each one — never submit an entity ID you're not confident about. If you
have no HA access, ask the person to open **Settings → Devices & Services →
Entities**, filter by domain (`switch.`, `sensor.`, etc.), and read you back
the exact entity IDs.

## 4. Walk through the config flow

In Home Assistant: **Settings → Devices & Services → Add Integration →
"ZoneFlow Irrigation"**. It's two screens:

**Screen 1 — zone name.** One field, `Zone name`: a short, human name (e.g.
"Front Lawn", "Avocado Tree", "Herb Bed"). This becomes the device name in
the HA UI and the default CSV log filename, so it must be distinct from any
other zone's name.

**Screen 2 — entities and schedule.** Fields, in the order they appear:

| Field | What it is | How to fill it in |
|---|---|---|
| Valve switch | the `switch.*` from §3 | required |
| Pump power sensor | the `sensor.*` from §3 | required |
| Rain gauge tip counter | the `counter.*`/`sensor.*` from §3 | required |
| Outdoor temperature sensor | the `sensor.*` from §3 | required |
| Phone notify target | a `notify.*` entity | optional — leave blank if none |
| Weather forecast source | a `weather.*` entity | optional — leave blank unless the person wants the forecast gate (§6.4); can be added later via the integration's Options |
| CSV log file path | a file path | accept the pre-filled default (`/config/zoneflow_<zone-name-slug>.csv`) unless the person has a reason to change it |
| Deep soak schedule time | `HH:MM:SS` | default `05:00:00` is reasonable for most climates (before sunrise, before daytime evaporation); ask if they have a strong preference |
| Routine irrigation schedule time | `HH:MM:SS` | default `05:30:00`, same reasoning |
| Deep soak trigger | Fixed time / before or after sunrise / before or after sunset | leave as "Fixed time" unless they specifically want sunrise/sunset-relative scheduling (§6.3) |
| Deep soak sun offset (minutes) | only relevant if the above isn't "Fixed time" | ask how many minutes before/after |
| Routine trigger | same options as deep soak trigger | same guidance |
| Routine sun offset (minutes) | only relevant if routine trigger isn't "Fixed time" | ask how many minutes before/after |

Submitting this screen creates the zone. It starts running on the schedule
immediately, but every tunable number below still has its factory default
until you set it in §5 — **do that before leaving the person alone with a
live valve.**

**If they asked for a dashboard card in §1:** this is the moment to note
this zone's real entity IDs, while you're already looking at its device
page for §4a and §5 anyway — don't wait until everything else is finished.
If you have HA tool access, list this zone's device's entities now (by
device name, or filtering `number.*`/`sensor.*`/`binary_sensor.*`/
`button.*`/`datetime.*` for the zone's slug) and keep the list. In Mode B,
ask the person to open the zone's device page (**Settings → Devices &
Services → [zone name]**) and read you every entity ID shown there, once,
while they're already on that screen for §4a/§5 — not as a separate ask
later. Either way, hold onto this list; §8 uses it directly instead of
looking anything up again.

### 4a. Seed the zone's history if it isn't actually brand-new

Ask this before moving on, every time: **"has this plant/zone already been
getting watered some other way, or is it genuinely starting from zero?"**

A newly-created zone has no watering history at all, which makes it look
overdue by default — left alone, it will run its first routine/deep-soak
cycle at the very next scheduled time, whether or not the plant actually
needs it yet. That's correct behavior for a genuinely new setup, but wrong
for someone migrating an already-established plant onto ZoneFlow (which is
the more common case in practice).

If the person says the plant has recent real watering/rain history, set the
zone's three `datetime` entities (found the same place as the number
entities — the zone's device page, or `datetime.<zone_name_slug>_*` in
Developer Tools → States) accordingly, using whatever they can tell you
(exact dates if they know them, otherwise "a few days ago" is fine — being
approximate here is much better than leaving it blank when it shouldn't be):

- **Last Routine Irrigation** — when it last got its normal/frequent watering
- **Last Deep Soak** — when it last got a deep, thorough watering
- **Last Significant Rain** — when it last actually rained enough to matter
  (not just a drizzle)

Setting these via the `datetime.set_value` service (or the UI date/time
picker) immediately changes the gating math — e.g. seeding "Last Deep Soak"
to today correctly makes the zone *not* due for another ~14 days. Leave any
of the three unset ("unknown") if the person genuinely doesn't know or it
really hasn't happened yet; that's the honest default and gates behave as
if it's simply never occurred.

## 5. Set the tunable numbers for this zone/crop

**Before suggesting any values, ask (or infer from context) two things if
you don't already know them: what's being watered (the crop/plant type),
and roughly where in the world this is (country or region is enough — you
don't need a precise location).** Climate varies enough between, say, the
tropics, a temperate continental climate, and a Mediterranean one that the
same crop genuinely wants different weekly targets and temperature
thresholds in each. Use both together, not just the crop table below in
isolation:

- **Hot/tropical climates** (e.g. Thailand, most of Southeast Asia, much of
  India, equatorial Africa/South America): lean toward the higher end of
  the crop ranges below, set the hot-weather temp threshold around
  30-32°C, and expect the "hot" tier to be in effect for a large fraction
  of the year rather than the exception.
- **Temperate climates** (e.g. much of Europe, the northern US, Finland):
  lean toward the lower end of the crop ranges, set the hot threshold
  around 26-29°C (a "hot day" is a lower bar than in the tropics), and the
  cool threshold matters more here since cool weather is common for a
  larger part of the year.
- **Arid/Mediterranean climates** (e.g. much of Australia, southern
  Europe, the US Southwest): similar targets to hot/tropical for the dry
  season, but watch the forecast dry-spell override (§6.4) — long genuine
  dry spells are normal here, not a sign the forecast gate is misbehaving.

These are starting points to reason from, not a lookup table to follow
blindly — say so if asked, and adjust based on anything more specific the
person tells you about their actual local conditions (a very hot
microclimate, unusually high humidity reducing evaporation, etc.) rather
than the country name alone.

After the config entry is created, several dozen `number.<zone>_*` entities
appear (Settings → Devices & Services → the zone's device → its entities,
or just search `number.<zone_name_slug>` in Developer Tools → States). Don't
make the person click through all of them one at a time — tell them (or set
directly, if you have HA control access) the handful that actually matter
for their crop, using this table. Everything not mentioned is fine left at
its factory default.

| Number entity (suffix) | What it controls | Suggest based on... |
|---|---|---|
| `..._routine_normal_weekly_target` (mm) | weekly water target in normal weather | crop water needs — see the quick table below |
| `..._routine_hot_weekly_target` (mm) | weekly target once it's classified "hot" | usually ~1.3x the normal target |
| `..._routine_cool_weekly_target` (mm) | weekly target once it's classified "cool" | usually ~0.7x the normal target |
| `..._hot_weather_temp_threshold` (°C) | 3-day avg peak temp that counts as "hot" | local climate — ask, or use ~31°C in the tropics, ~28°C in temperate zones |
| `..._cool_weather_temp_threshold` (°C) | 3-day avg peak temp that counts as "cool" | local climate — usually 5-8°C below the hot threshold |
| `..._emitter_flow_rate_calibration` (mm/min) | **critical** — how fast the emitters actually apply water | ask the person for their drip/sprinkler flow rate, or help them calculate it: run `zoneflow.test_pulse` for a known number of minutes, measure water depth/volume delivered, divide. Do not guess this one; a wrong value makes every runtime calculation wrong. |
| `..._deep_soak_target_depth` (mm) | depth for the infrequent deep-soak cycle | deeper-rooted / drought-tolerant plants (trees, established shrubs) want more (25-40mm); shallow-rooted beds want less (15-20mm) |
| `..._deep_soak_max_safety_runtime_cap` / `..._routine_max_safety_runtime_cap` (min) | hard abort ceiling — if the calculated runtime for a cycle exceeds this, that cycle is aborted rather than run, since it usually means a miscalibration | **check this for very low-flow drip emitters** (below roughly 0.1mm/min): the calculated runtime for a full target can genuinely run into several hundred minutes, and the factory default caps (124min / 103min) will wrongly abort a perfectly correct, just-slow cycle. Raise the cap (up to 900min) to comfortably cover `target_mm / flow_rate_mm_per_min` for this zone's real numbers — don't just raise it blindly to max "to be safe," since its whole job is catching a genuine miscalibration (e.g. a wrong flow-rate number producing a runaway runtime). |
| `..._pump_low_power_warning_threshold` (W) | pump-power audit floor | ask for the pump's rated running wattage, set ~20-30% below it |
| `..._routine_dry_down_holdoff` (days) | holdoff after significant rain before routine resumes | shallow-rooted/thirsty plants: lower (1-2d); drought-tolerant: higher (4-6d) |
| `..._deep_soak_subsoil_dry_down_holdoff` (days) | same, for deep soak | usually higher than the routine holdoff — trees/deep roots hold subsoil moisture longer |
| `..._pump_preamble_warm_up_delay` (s) / `..._pump_postamble_settle_delay` (s) | only relevant if this zone shares a pump with another zone (§6.2) | leave at 0 for a single-zone/independent-pump setup |
| `..._forecast_rain_skip_threshold` (mm) / `..._forecast_rain_probability_threshold` (%) / `..._forecast_dry_spell_override` (days) | only relevant if a weather entity was set (§6.4) | see §6.4 |

**Quick weekly-water-target starting points by crop type** (mm/week, normal
weather — adjust from here rather than treating these as exact):
- Lawn / turf: 25-35mm
- Vegetable beds, herbs (shallow roots, frequent light watering preferred): 20-30mm, and prefer a lower routine interval logic — this integration adapts the interval automatically via temperature, so you mainly need the weekly target right
- Established trees / avocado / fruit trees: 25-45mm routine **plus** rely on the deep-soak cycle (20-30mm depth) for root-zone penetration
- Succulents / drought-tolerant natives: 10-20mm, and set the dry-down holdoffs and forecast dry-spell override (if used) higher

These are reasonable starting points, not agronomy guarantees — say so if
the person asks, and suggest they watch the diagnostic sensors (§7) for the
first couple of weeks and adjust the weekly target up/down from there.

## 6. Situational features — ask only if relevant

### 6.1 Multiple zones
If the person has more than one plant/area to water, repeat §3-§5 for each
zone (Add Integration → ZoneFlow Irrigation again, with a different zone
name and its own entities). Nothing extra to configure for this by itself.

### 6.2 Shared pump
If two zones' **pump power sensor** is the same entity, ZoneFlow
automatically detects this and makes sure they never run at once — nothing
to configure. If their pump needs a moment to build pressure, set
`pump_preamble_seconds` (delay after the pump starts before the valve
opens) and/or `pump_postamble_seconds` (delay after the valve closes before
the next queued zone can start) on the zones that share that pump. Ask the
person if their pump has a noticeable spin-up/pressure-settle time; if they
don't know, leave both at 0 and revisit only if they see flow-rate
inconsistency between zones.

### 6.3 Sunrise/sunset-relative scheduling
If the person wants watering tied to daylight rather than a fixed clock
time (e.g. "start 30 minutes before sunrise" so it adapts across seasons),
set the relevant trigger field (in §4's table) to one of Before/After
Sunrise/Sunset and fill in the offset in minutes. This is independent per
schedule (deep soak and routine can each use a different mode).

### 6.4 Weather forecast gate
Only set this up if the person wants ZoneFlow to skip a scheduled run when
rain is forecast. Requires a `weather.*` entity (any integration that
provides one — ask which weather integration they use, or find it via §3).

1. Set the zone's "Weather forecast source" field to that entity (in the
   config flow, or later via the integration's **Options** if already set up).
2. Ask how much forecasted rain should count as "skip this run" — default
   is 3mm. Thirstier/more rain-sensitive setups can lower it; if the person
   wants to be conservative about not missing water, raise it.
3. Ask about the **dry-spell override** (`forecast_dry_spell_override`,
   default 2 days) — **this is the one number worth actively discussing per
   crop**, since it's exactly "how many days can this plant go if the
   forecast keeps promising rain that never comes":
   - Thirsty, shallow-rooted, or heat-stressed plants (seedlings, potted
     plants, vegetables in hot weather): set it low, 1-2 days.
   - Established, drought-tolerant plants (trees, succulents, natives): set
     it higher, 4-7 days — they can comfortably wait out a longer stretch of
     wrong forecasts.
   Explain the mechanic briefly if asked: the gate only ever *delays* a
   watering, never skips it outright — once the configured number of days
   passes with the forecast still saying rain but zero rain actually
   measured, ZoneFlow overrides the forecast and waters anyway. A missing or
   unavailable weather entity never blocks a run either.

## 7. Verify before you're done

Do not consider setup finished until these are confirmed for each zone:

1. Run **Developer Tools → Actions → `zoneflow.test_pulse`** with
   `seconds: 10` (targeting that zone's device, since each zone is its own
   config entry/service target if the person has multiple). Confirm: the
   valve entity actually switches on then off, the pump-power sensor reads
   a plausible non-zero value while it's on, and a new row appears in the
   configured CSV log file.
2. Check the zone's diagnostic sensors exist and show sane values: rain
   past 24h/3d/7d/14d, 3-day average peak temperature, next-irrigation
   estimate.
3. Confirm the lock/abort binary sensors both read "off"/`False` at rest —
   if either is stuck on, something is wrong before you hand this back to
   the person unattended (`zoneflow.reset_lock` clears a stuck lock, but
   find out why it was stuck first).
4. Tell the person plainly what will happen next (which zones water at
   which times) and remind them the `test_pulse` service bypasses every
   safety/rain gate on purpose, so it's not representative of a real run —
   don't leave them thinking a successful test pulse alone proves the rain
   logic works.
5. **Check whether they said yes to a dashboard card back in §1.** If they
   did, setup is *not* finished until §8 is actually done and the person
   has the finished YAML in hand — not just noted as something you'll get
   to. It's easy to reach this point, confirm the test pulse and sensors
   look good, and declare the job done without circling back to a "cosmetic
   extra" from several steps ago. Don't let that happen: treat a yes on the
   dashboard card exactly like any other item on this list — required
   before you say setup is complete, not an afterthought you can skip if it
   slips your mind.

## 8. Optional finishing touch: build a dashboard card for this zone

This only applies if the person said yes to this back in §1. Everything
above gets a zone *working* — this step is purely cosmetic, and skip it
outright if they never asked or said the default device page is fine.

The goal is a dashboard section that groups this zone's entities the way a
person actually thinks about them (status, manual controls, targets, safety)
instead of HA's default alphabetical device-page list. Do **not** hand the
person a generic template with guessed entity IDs — HA's own slugification
of punctuation (dashes, parentheses, "+") is inconsistent enough that a
guessed ID is frequently wrong by one character. That's exactly why §4
already had you collect this zone's real entity IDs while you were on its
device page for §4a/§5 — use that list now instead of looking anything up
again:

1. Take the entity ID list you collected back in §4. If for some reason you
   skipped that (the person changed their mind about wanting a card only
   after setup was already finished), do it now the same way: HA tool/API
   lookup by device name or by filtering `number.*`, `sensor.*`,
   `binary_sensor.*`, `button.*`, `datetime.*` for the zone's slug, or ask
   the person to read the IDs off **Settings → Devices & Services → their
   zone's device**.
2. Fill the template below with those confirmed IDs — every `<entity.id>`
   placeholder — so what you hand back is genuinely paste-ready, not a
   fill-in-the-blanks exercise for the person.
3. Tell them exactly where to paste it: **Settings → Dashboards → (their
   dashboard) → ⋮ Edit Dashboard → ⋮ Raw configuration editor**, then either
   paste this as a new item under an existing `views:` list, or as a whole
   new dashboard if they don't have a YAML-mode one yet. If they're on the
   default auto-generated dashboard (most first-time users are), point them
   at **Settings → Dashboards → + Add Dashboard → "New dashboard from
   scratch"** first, since the auto-generated one can't be hand-edited.

Template — one `views:` entry per zone, using only plain built-in cards (no
extra HACS frontend dependency required):

```yaml
title: <Zone Name>
path: <zone-slug>
icon: mdi:sprinkler
cards:
  - type: entities
    title: Status
    show_header_toggle: false
    entities:
      - entity: <switch.valve_entity>
        name: Valve
      - entity: <binary_sensor.zone_irrigation_abort_flag>
        name: Abort Flag
      - entity: <sensor.zone_pump_power_entity_if_relevant>
        name: Pump Power
      - entity: <sensor.zone_next_irrigation_estimate>
        name: Next Run Estimate

  - type: entities
    title: Manual Controls
    show_header_toggle: false
    entities:
      - type: buttons
        entities:
          - entity: <button.zone_run_deep_soak>
            name: Run Deep Soak
            icon: mdi:waves
          - entity: <button.zone_run_routine_irrigation>
            name: Run Routine
            icon: mdi:play
          - entity: <button.zone_reset_lock>
            name: Reset Lock
            icon: mdi:lock-open-variant

  - type: entities
    title: Routine Irrigation
    show_header_toggle: false
    entities:
      - entity: <number.zone_routine_normal_weekly_target>
      - entity: <number.zone_routine_hot_weekly_target>
      - entity: <number.zone_hot_weather_temp_threshold>
      - entity: <number.zone_routine_cool_weekly_target>
      - entity: <number.zone_routine_dry_down_holdoff>

  - type: entities
    title: Deep Soak (14-Day)
    show_header_toggle: false
    entities:
      - entity: <number.zone_deep_soak_target_depth>
      - entity: <number.zone_deep_soak_rain_ceiling>
      - entity: <number.zone_deep_soak_subsoil_dry_down_holdoff>

  - type: entities
    title: Forecast Gate & Dry-Spell Override
    show_header_toggle: false
    entities:
      - entity: <number.zone_forecast_rain_skip_threshold>
      - entity: <number.zone_forecast_rain_probability_threshold>
      - entity: <number.zone_forecast_dry_spell_override>

  - type: entities
    title: Calibration & Safety Caps
    show_header_toggle: false
    entities:
      - entity: <number.zone_emitter_flow_rate_calibration>
      - entity: <number.zone_rain_gauge_mm_per_tip>
      - entity: <number.zone_pump_low_power_warning_threshold>
      - entity: <number.zone_deep_soak_max_safety_runtime_cap>
      - entity: <number.zone_routine_max_safety_runtime_cap>

  - type: entities
    title: History Seeding
    show_header_toggle: false
    entities:
      - entity: <datetime.zone_last_routine_irrigation>
      - entity: <datetime.zone_last_deep_soak>
      - entity: <datetime.zone_last_significant_rain>

  - type: markdown
    title: Zone Trigger Log
    content: |
      {% set abort = states('<binary_sensor.zone_irrigation_abort_flag>') %}
      {% set routine_ts = states('<datetime.zone_last_routine_irrigation>') %}
      {% set deep_soak_ts = states('<datetime.zone_last_deep_soak>') %}
      | Field | Value |
      | :--- | :--- |
      | **Abort Flag** | {{ 'PROBLEM' if abort == 'on' else 'OK' }} |
      {% if routine_ts not in ['unknown', 'unavailable', none] %}
      | **Last Routine Irrigation** | {{ as_timestamp(routine_ts) | timestamp_custom('%b %d, %H:%M') }} |
      {% endif %}
      {% if deep_soak_ts not in ['unknown', 'unavailable', none] %}
      | **Last Deep Soak** | {{ as_timestamp(deep_soak_ts) | timestamp_custom('%b %d, %H:%M') }} |
      {% endif %}
```

If the person has multiple zones, repeat the whole `cards:` block as another
`views:` entry (one tab per zone) rather than stacking every zone's cards
into a single long page — mirrors how the entities themselves are already
split one config entry per zone.

One honest caveat to pass on to the person: this is plain built-in HA
cards, chosen deliberately so nothing extra needs installing. It won't look
as polished as a purpose-built dashboard (gauges, sparklines, a custom
panel) — if they want that, it's a separate, bigger undertaking outside
what this integration ships with.

## 9. Ground rules while you do this

- Never guess an entity ID and submit it without the person confirming it,
  or without your own tool-based lookup giving you real confidence.
- Never disable or bypass a safety watchdog (stuck-valve force-off,
  power-loss abort, stale-lock recovery) — these aren't configurable by
  design, and that's intentional; don't suggest workarounds.
- Don't touch `custom_components/zoneflow/calculations.py` or any other
  integration source file as part of "setup" — setup is entity selection +
  number tuning through the UI, never a code change.
- If something doesn't fit this guide (an entity type you can't find, a
  request to change scheduling logic itself, an error message not covered
  here), say so plainly and point the person at opening a GitHub issue,
  rather than improvising a change to how the integration behaves.
