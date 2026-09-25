# ZoneFlow — AI Setup Guide

> **If you are an AI assistant reading this file because a person asked you
> to help them set up ZoneFlow: this whole file is written for you.** Follow
> it top to bottom. The person should not need to open any other doc in this
> repo, and you should not need to ask them anything not listed here.
>
> Drive the conversation on everything that's actually clear: ask one
> question (or one small group of related questions) at a time, use
> sensible defaults instead of asking about every field, and get the
> integration actually configured and running a test pulse before you
> consider the job done. Do not explain ZoneFlow's internal architecture
> unless asked — the person wants working irrigation, not a code tour.
>
> **But "drive the conversation" never means "push through uncertainty to
> reach completion."** If you can't confidently tell which entity, value,
> or setting applies, that uncertainty is itself a valid reason to stop and
> ask — never pick the plausible-looking option just to keep moving. A
> half-finished, honestly-flagged setup is a fine place to pause; a
> fully-finished setup built on a guessed entity or a guessed number is
> not a good outcome even though it looks like one.
>
> Gauge how comfortable this specific person is with Home Assistant from
> how they talk, in the first couple of exchanges — don't ask this as its
> own formal question. Someone who's clearly done this before can be moved
> through quickly with normal HA terminology. Someone who seems unsure, or
> says so outright, deserves shorter steps, one screen at a time, plain
> language over jargon (say "the switch that turns your valve on" before or
> instead of "a `switch.*` entity"), and more frequent "does that make
> sense so far?" checks. Recalibrate as you go if they turn out more or
> less comfortable than your first read suggested.
>
> **Whenever the person seems stuck, confused, or unsure what they're
> looking at, remind them they can just take a screenshot of their screen
> and paste it into the chat.** You can read a screenshot directly and say
> exactly what to click next — this is often faster and far less
> frustrating than a back-and-forth of "I don't see that" / "it's the icon
> in the top right" written out in words. Mention this possibility once,
> early on (so it's a known option rather than a rescue they have to think
> to ask for), and again anytime they sound lost. The first time you
> suggest it, add one honest line: a full-screen HA screenshot can catch
> more than intended — camera feeds, other people's names, notifications,
> exact location — so cropping to just the relevant panel is worth doing
> when that's quick, and either way it stays private to this conversation,
> never posted anywhere public.

> **Non-negotiable, before anything else below:**
> - **Scope lock: you are here to set up ZoneFlow, nothing else.** If you
>   have tool/API access to the person's real Home Assistant (Mode A —
>   §1a), that access is scoped to this task only. Never modify, delete,
>   rename, or "clean up" any existing entity, automation, script, helper,
>   dashboard view, or config entry that isn't the new ZoneFlow zone you
>   were asked to create — not even something that looks obviously broken,
>   redundant, or improvable. And never volunteer improvement suggestions
>   about their wider setup unprompted — no "by the way, I noticed your
>   automation X could be optimized." If something you encounter along the
>   way looks like a real problem in their existing setup, you may mention
>   it once, plainly, and then drop it unless they ask you to act on it —
>   never fix it yourself as a side effect of this setup. This exists
>   because AI assistants overstepping scope on live Home Assistant configs
>   has caused real, painful damage before; the same caution this project's
>   own maintainer requires of any AI touching their production system
>   applies here to everyone using this guide, on every instance,
>   every time — the boundary is not a suggestion.
> - Never guess an entity ID, and never decide one on the person's behalf —
>   confirm every single one with the person before submitting it, even one
>   your own tool-based search turned up as an apparently-obvious match.
>   **This has no "it's just a test/demo/sandbox setup" exception.** A test
>   run through this guide uses exactly the same process as a real one: ask
>   about every entity, at every step, the same as you would for the
>   person's actual production system. Don't quietly fill in whatever
>   entity happens to exist in a sandbox because asking felt unnecessary for
>   "just a test" — if you need entities that don't exist yet to exercise a
>   step, say so and ask whether to create them or which real ones to reuse,
>   rather than picking for the person.
> - Never disable, bypass, or suggest a workaround for a safety watchdog
>   (stuck-valve force-off, power-loss abort, stale-lock recovery). Not
>   configurable by design.
> - Never edit `calculations.py` or any other integration source file as
>   part of "setup" — this is entity selection + number tuning through the
>   UI only, never a code change.
> - If something doesn't fit this guide, say so plainly and offer to draft a
>   GitHub issue (§10 covers exactly how, including a hard privacy rule on
>   what must never appear in it) rather than improvising a code change.

## 0. What you're setting up, in one paragraph

ZoneFlow is a Home Assistant custom integration for drip/valve irrigation.
Each **zone** (one plant, bed, or lawn area with its own valve) is added as
its own separate config entry, done through Home Assistant's normal "Add
Integration" UI flow — there is no YAML to write. The only entity ZoneFlow
truly requires is the valve switch; a rain gauge, outdoor temperature
sensor, pump-power sensor, and flow meter are all optional and each
degrades gracefully on its own when left out (§2 explains exactly what each
one buys you, so the person can make an informed choice rather than feeling
like they need hardware they don't have to get started). Your job is to (a)
work out what to put in each field of that flow and each crop-relevant
tunable number, and (b) either enter it yourself (if you have tool access
to their Home Assistant — §1a) or tell the person exactly what to click and
type (if you don't — §1).

## 1. First questions — ask all together, before anything else

Before touching §2, ask the person these things **in one go, as a single
batch** — not spread across the conversation, not deferred, and never
silently defaulted because a later section calls a field "optional." An
unanswered optional field is not the same as a "no."

1. **How many zones total?** Get the total count up front, even if you're
   only going to configure the first one right now. This is what tells you
   to keep going through §2-§9 again for zone 2, zone 3, etc. instead of
   stopping after the first zone and leaving the rest for the person to
   somehow figure out is still needed. If they don't know yet (e.g. "at
   least one, maybe more later"), that's fine — just don't assume "one"
   silently when they said something else.
2. **Mode A or Mode B?** Check your own available tools/functions right now
   for anything that looks like Home Assistant control — an MCP server
   exposing calls like `ha_call_service`/`ha_set_entity`/`ha_get_state`, a
   Home Assistant connector, or a long-lived access token you've been
   given. Don't just ask the person whether they have this set up — look
   first, then tell them plainly what you found ("I do have Home Assistant
   tool access available" / "I don't see any Home Assistant tools
   available to me right now").
   - **If you found tool access:** don't assume it's pointed at *their*
     instance just because it exists — confirm that before touching
     anything ("I have Home Assistant tools available — is this already
     connected to your actual system, or is this a demo/different
     instance?"). Once confirmed, ask whether they'd rather you configure
     it directly (**Mode A**) or walk them through clicking it themselves
     (**Mode B**) — some people want to watch/learn the UI, most want it
     just done. Before making any change in Mode A, it's worth mentioning —
     as a suggestion, not a blocker — that a quick **Settings → System →
     Backups → Create Backup** first costs a minute and means anything you
     do here is trivially undoable; proceed either way once they answer,
     don't insist on it.
   - **If you found no tool access:** say so, then offer a real choice
     instead of silently defaulting to Mode B: (a) walk them through
     connecting one now — Home Assistant has a built-in **"Model Context
     Protocol Server"** integration (Settings → Devices & Services → Add
     Integration → search "Model Context Protocol Server") that exposes
     their instance to compatible AI tools, so this (or a future) session
     could use Mode A (if that integration offers a way to limit which
     entities it exposes, similar to Assist's "Expose" settings, mention
     that scoping it to just this zone's entities is worth doing — but
     don't hold up the setup hunting for that option if it's not obvious);
     (b) proceed in **Mode B** (you guide, they click)
     right now, no setup needed — this is a perfectly complete way to
     finish the whole setup; or (c) if they'd rather not set anything up,
     mention that some other AI assistant/session might already have this
     kind of access configured, and they're welcome to paste this same
     guide there instead. Don't steer them toward any one option —
     whichever is less hassle for them is the right one.
   - **If they go with (a) — setting up a brand-new connection just for
     this:** say plainly, before they spend the effort connecting it, that
     this works best on a paid AI plan. Tool/API calls (each entity lookup,
     each config write) burn through a free usage allowance much faster
     than plain chatting, and running out partway through — after already
     wiring up the connection — is a worse outcome than never having
     started that way. This warning is specifically for *new* connections
     made for this setup, not a blanket rule: if they already had tool
     access configured before asking for help (the first bullet above),
     they already know what their own setup can do and don't need this
     spelled out — just proceed. If they're on a free plan and would
     rather not risk it, Mode B remains the simplest safe default: it's
     plain conversation with no tool calls, so there's nothing to run out
     of mid-setup. If a **long-lived access token** (rather than the MCP
     Server integration) is how this connection gets made, mention once
     that it's worth revoking (**Settings → Your profile → Security →
     Long-lived access tokens**) after setup if they don't plan to keep
     using AI-driven control day to day — a token left lying around in a
     chat session/config file is a standing credential, not a one-time key.
3. **What exactly is being watered, and where?** Ask this as a genuinely
   open question — "what plant/crop is this?" — never as a multiple-choice
   pick from a handful of broad categories (even with a free-text
   "other/something else" escape hatch). A preset list anchors people
   toward whichever option sounds closest, and correct watering depends on
   the actual, specific plant, not the nearest-sounding category — a
   pumpkin and a cucumber are both "vining vegetables" but want different
   numbers. Also get roughly where in the world this is (country/region is
   enough). The moment you have a specific plant name, **do real research
   on it** (web search) rather than leaning only on §5's quick-reference
   table, which only covers a handful of broad categories — look up its
   typical root depth, weekly water needs, whether it actually benefits
   from an infrequent deep soak versus frequent shallow watering (§6a), and
   roughly how many days from planting to maturity/fruiting (useful for
   §6's growth-ramp curve later). Bring this research to the person as a
   suggestion they can confirm or correct, not as a silent internal
   decision.
4. **Outdoors, in a greenhouse, or otherwise indoors?** Don't leave this
   for later — it changes real decisions: whether the weather forecast
   gate (§7.4/question 7 below) is even useful for this zone (it isn't,
   for a greenhouse or indoor space), and what an "outdoor temperature"
   sensor should actually be measuring for it (§2 has the full detail once
   you know the answer).
5. **Slope?** This one's easy to just ask outright rather than explain at
   length: is the ground this zone sits on flat, a slight slope, a
   moderate slope, or steep? (A person can usually answer this from memory
   without going to look at anything, unlike soil type below — that's why
   it's worth getting out of the way immediately.) It's descriptive/
   informational only (§4's table says more), so "not sure" is a fine
   answer if they genuinely don't know.
6. **Dashboard card, and/or a plain-language cheat sheet?** Two separate,
   independent, purely-cosmetic offers — ask about both, don't assume one
   implies the other: (a) a ready-to-paste dashboard YAML for this zone
   (§9), and (b) a short, jargon-free cheat sheet (§9a) covering what this
   zone does day to day and exactly what to click for the two or three
   things a person actually does by hand (run a cycle now, reset a stuck
   lock). A dashboard shows numbers; a cheat sheet explains what they mean
   in plain words — worth offering separately since the second one matters
   most for anyone less technical who'll also use this zone day to day (a
   housemate, family member, or just future-them after months away from
   HA's UI). Either answer changes what you need to track during §4.
7. **Phone notifications?** ZoneFlow can alert a `notify.*` target on
   things like a stuck-valve force-off or a low pump-power warning. Do they
   want this, and if so, which `notify.*` entity?
8. **Weather forecast gate?** Point this zone at a `weather.*` entity to
   hold off watering when rain is forecast (§7.4). Do they have one they'd
   like to use here? Skip offering this one at all if question 4 said
   greenhouse/indoor (see §2 for why).

Carry all these answers forward — don't re-ask any of them later, and don't
let §4's config-flow table talk you back into treating an unanswered field
as a default "no." Specifically:

- **Zone count** governs how many times you repeat §2 through §9 in this
  conversation — after finishing one zone, move straight to the next one
  rather than stopping and waiting to be told to continue, unless the
  person asked you to pause.
- **Mode** decides the mechanism for every step in §2 through §8 (you
  clicking via tool access vs. telling them what to click) — the
  information gathered is identical either way. See §1a for Mode A's
  concrete calls.
- **Crop/region (+ your research on it)** feeds §5's starting-point
  suggestions (weekly targets, root depth, split-cycle pulse tuning), §6a's
  deep-soak recommendation, and, if they turn on growth-stage auto-ramp
  (§6), which ramp profile fits.
- **Environment (outdoor/greenhouse/indoor)** fills §2's greenhouse-specific
  handling and rules the forecast gate in or out.
- **Slope** fills straight into §4's "Slope" field — don't ask it again
  there.
- **Dashboard and/or cheat sheet = yes (either one)** means: while walking
  through §4 and §4a, note this zone's entity IDs as you naturally
  encounter them, instead of having to go back and rediscover them from
  scratch after everything's set up — both §9 and §9a need the same list.
  Skip whichever one they didn't ask for, and don't bring it up again
  unless asked.
- **Notifications = yes** means: collect the `notify.*` entity now, and
  fill it into §4's "Phone notify target" field. If no, that field stays
  blank in §4 — but because they were actually asked, not because you
  defaulted it.
- **Weather gate = yes** means: collect the `weather.*` entity now, fill it
  into §4's "Weather forecast source" field, and walk them through §7.4's
  threshold numbers once the zone exists. If no, that field stays blank.

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
   response disagrees; the live response is ground truth — this matters
   more now than it used to, since several fields in that schema are
   genuinely optional and simply won't appear in the response at all if
   you don't set them).
3. `POST /api/config/config_entries/flow/<flow_id>` again with the full
   entities/schedule payload (all the fields from §4's table, keyed exactly
   as the schema names them — **omit a key entirely** for any optional
   entity field the person is skipping; do not send it as `null` or `""`,
   which the schema rejects). A successful response has
   `"type": "create_entry"` and includes the new `result` (the config
   entry). An error response has `"type": "form"` again with an `errors`
   object — fix and resubmit, don't guess blindly at what changed.
4. Once created, the zone's `number.*` entities exist with factory
   defaults. To set one from §5's table, call the `number.set_value`
   service: `POST /api/services/number/set_value` with
   `{"entity_id": "number.<zone>_<field>", "value": <float>}`. Confirm
   afterwards by reading the entity's state back
   (`GET /api/states/<entity_id>`) rather than assuming the call worked.
5. To run the verification pulse from §8: `POST /api/services/zoneflow/test_pulse`
   with `{"entity_id": "<any entity belonging to that zone's device>", "seconds": 10}`
   (or however your tool's service-call helper targets a specific config
   entry/device — some MCP servers want a device_id instead of an
   entity_id; check your tool's own parameters rather than assuming this
   shape). Then read back the valve (and pump-power/flow-meter states, if
   configured) to confirm the pulse actually happened.

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
3. **What hardware/sensors do they actually have?** Only the **valve
   switch** is truly required — ZoneFlow cannot irrigate without something
   to open. Everything else is optional, and each one degrades gracefully
   on its own when left unset rather than being blocked or half-broken.
   Walk through this plainly rather than assuming they need all four before
   they can start — someone with just a valve can still get real, working
   automatic irrigation today, add sensors later, and nothing about setup
   has to be redone when they do:

   | Sensor | What it's for | What's lost without it |
   |---|---|---|
   | Rain gauge tip counter | rain-aware watering (skip/reduce when it's already rained) | rain-aware gates simply never fire — ZoneFlow waters on a temperature-driven schedule only, same as if it never rains |
   | Outdoor temperature sensor | hot/cool weekly-target tiers | the hot/cool tier logic falls back to the "normal" tier permanently — one flat weekly target year-round |
   | Pump power sensor | confirms the pump is actually drawing current during a pulse (a safety/reliability audit, not a control) | no low-pump-power warning if the pump fails silently mid-cycle |
   | Flow meter (cumulative-volume sensor) | measures actual water delivered per cycle, and can flag "pump ran but no water moved" | no "Last Cycle Water Delivered" reading and no no-flow-detected check |

   **Recommend having at least one of pump-power or flow-meter, for
   reliability** — without either, ZoneFlow has no way to notice a pump
   that's running dry, clogged, or disconnected; it'll faithfully open and
   close the valve on schedule with no idea whether water actually moved.
   Say this plainly as a recommendation, not a requirement — plenty of
   setups run fine without either, they just lose that one safety net.

4. Ask them, in one message, for the physical setup of the **first zone**
   they want to configure — crop/plant and environment (outdoor/greenhouse/
   indoor) should already be in hand from §1's batch (questions 3 and 4);
   don't re-ask them here, just carry them forward and apply the
   greenhouse-specific handling below if relevant.

   **Ask about each sensor in the table above by name, individually — never
   as one lumped "which of these do you have" line that's easy to answer
   incompletely, and never silently checked off as "probably not set up
   yet" for a test/sandbox instance.** Almost everything here is optional,
   which is exactly why none of it can be assumed either way — "optional"
   means "ask, and the answer might genuinely be no," never "skip asking
   and default to no because most fields are optional anyway." Ask each of
   these as its own short yes/no, every time, for every zone:
   - **"Do you have a rain gauge?"** — either answer leads into §2a right
     below before moving on.
   - **"Do you have an outdoor temperature sensor"** (or, for a greenhouse/
     indoor zone, "one that reads this specific zone's actual growing-area
     temperature, not the outside air")?
   - **"Do you have a pump power sensor?"**
   - **"Do you have a flow meter?"**

   Whichever they say no to is simply left unset in §4 — a normal, fully-
   supported configuration, not a problem to solve before continuing. But
   don't decide "no" on their behalf, and don't skip a search in §3 for one
   they said yes to just because it felt like extra steps.

   **If this zone is a greenhouse/indoor setup:**
   - **Always ask, explicitly, every time this comes up: "Can real rain
     actually get into the greenhouse?"** (open roof vents, gaps, a
     structure that's more of a rain shelter than sealed — versus a fully
     enclosed structure that never sees outside weather). Never assume
     either way and never skip the question because it feels obvious from
     how the rest of the conversation has gone.
   - **Default to skipping both the rain gauge and the weather forecast
     gate for this zone unless the answer is a genuine yes.** These two
     go together because they answer the same underlying question — does
     outside weather reach these plants — so treat them as one decision,
     not two separate ones to ask about independently:
     - **Weather forecast gate**: don't offer it for this zone, even if
       you already have a `weather.*` entity from another (outdoor) zone.
       A forecast of rain outside doesn't mean this zone should hold off —
       real rain never reaches these plants when the answer is no.
     - **Rain gauge**: leave it unset for this zone by default. A
       greenhouse zone that genuinely never sees the gauge tip would just
       read zero rain forever, which is harmless but also pointless to
       wire up — better to leave it unset and say so, so the person isn't
       maintaining a sensor that can't do anything for this zone.
   - **If the answer is yes** — vents open, the structure lets real rain
     through — set up both the rain gauge and the weather forecast gate
     for this zone exactly as you would for an outdoor zone; there's
     nothing greenhouse-specific left to special-case once rain genuinely
     reaches the plants.
   - If they have an "outdoor temperature" sensor, make sure it's
     whatever actually measures **this zone's real ambient conditions** —
     a sensor physically inside the greenhouse, not a literal
     outside-the-building sensor. A greenhouse commonly runs hotter than
     the outside air, and that temperature is what drives the hot/cool
     tier classification (§5) for this specific zone.

### 2a. Rain gauge: calibration, or building one if they don't have one

   **If they have a rain gauge**, ask whether they already know its
   mm-per-tip calibration value — the depth of rainfall over the gauge's
   catchment area that one tip of the bucket represents; this feeds the
   `rain_mm_per_tip` number in §5's table. Two paths from here:
   - **They know it** — use that value directly, nothing more to ask.
   - **They don't know it** — ask what brand/model the gauge is (e.g.
     "Misol," a specific WH-model number, "Ambient Weather," etc.) and look
     it up (web search) for its published mm-per-tip spec as a starting
     point — most mechanical tipping-bucket gauges document this, commonly
     somewhere in the 0.2-0.5mm/tip range depending on model and funnel
     size. Say plainly that this is the manufacturer's figure standing in
     for a real measurement, not something you've confirmed for their
     specific unit, and offer the more precise alternative for anyone who
     wants it: pour a known amount of water slowly into the gauge's funnel,
     count how many tips it produces, then divide (water depth ÷ tip count)
     — genuinely more accurate since it captures that individual unit's
     actual catchment area and any manufacturing variance, but entirely
     optional if the looked-up factory figure is good enough for them.

   **If they don't have one**, recommend getting one rather than quietly
   leaving rain-aware watering off — of the four optional sensors in §2's
   table, it's one of the cheaper, more worthwhile additions (without it,
   ZoneFlow waters on a temperature-only schedule with no idea it already
   rained). Offer both routes and let them pick:
   - **A ready-made wireless rain-gauge console** with its own Home
     Assistant integration or an MQTT bridge — several weather-station
     brands support this — the simpler route if they'd rather just buy
     something that works out of the box.
   - **A cheap DIY build**, for anyone who'd rather not buy a whole
     weather-station console just for the rain gauge: a bare mechanical
     tipping-bucket rain gauge (sold on its own, no electronics, roughly
     $15-25) already has a magnetic reed switch inside that closes briefly
     on every tip. Wire that reed switch's two leads into a spare Zigbee/
     Z-Wave door-and-window contact sensor's dry-contact terminals (or an
     ESPHome board's GPIO input) in place of the gauge's own wireless
     console — Home Assistant then sees each tip as an ordinary open/close
     event on that contact sensor. From there, add a `counter:` helper (or
     a template sensor that increments on the contact's state changes) so
     there's a genuinely cumulative, always-increasing entity to point
     ZoneFlow's "Rain gauge tip counter" field at. This is a real,
     low-cost, commonly-used approach — a spare contact sensor is often
     already on hand or costs only a few dollars, versus buying an entire
     wireless rain-gauge console.

   Either way, say plainly that this is a "worth adding for reliability"
   recommendation, not a blocker — a zone runs fine with no rain gauge at
   all, on the temperature-driven schedule alone, and setup can absolutely
   continue today without one.

## 3. Find the entity IDs

If you have HA tool/API access, search for candidates and propose them
rather than asking the person to hunt for IDs blind. Only search for a
sensor the person actually said they have (§2) — don't go hunting for a
pump-power sensor to fill in "just in case" if they told you they don't
have one.

- Valve: a `switch.*` entity that plausibly controls water flow (name
  hints: "valve", "water", "irrigation", "zone", the crop name they gave
  you).
- Rain counter (optional): a `counter.*` or `sensor.*` entity that only
  increases (a tipping-bucket rain gauge's raw tip count, or a cumulative
  mm sensor).
- Outdoor temperature (optional): a `sensor.*` with device class
  `temperature`.
- Pump power (optional): a `sensor.*` entity reporting watts (name hints:
  "pump", "power"). This is used to confirm the pump is actually drawing
  current during a pulse, not to control the pump.
- Flow meter (optional): a `sensor.*` reporting a cumulative volume (name
  hints: "flow", "water meter", "liters"/"litres"/"gallons") — must be
  cumulative (always increasing), the same shape as the rain counter, not
  an instantaneous flow-rate reading. If more than one zone will point at
  the same flow meter entity, ask where it's physically plumbed relative
  to those zones' valves and pumps before assuming that's fine as-is —
  see §7.2a, since a meter shared across genuinely different pumps changes
  how those specific zones queue.
- Notify target: a `notify.*` entity for phone alerts — only look for this
  if they said yes to notifications in §1; skip this search entirely if
  they said no.
- Weather: a `weather.*` entity for the forecast gate (§7.4) — only look
  for this if they said yes to the forecast gate in §1; skip it if not.

Present your best-guess matches and ask the person to confirm or correct
each one — never submit an entity ID you're not confident about, and never
treat your own search as the confirmation. This applies exactly as much to
a test, demo, or sandbox instance as to someone's real production Home
Assistant — "it's just a test" is never a reason to pick an entity yourself
instead of asking. If a needed entity doesn't exist at all yet (common in a
sandbox), say so and ask the person whether to create one or which existing
one to point at instead; don't silently invent or select one to keep the
walkthrough moving.

### 3a. If you have no HA tool access: don't make them hunt blind

First, reassure them this is easier than it sounds: **when they get to §4's
"Add Integration" form, every entity field is already a searchable dropdown
of friendly names, filtered to only the relevant kind** (the valve field
only lists switches, the temperature field only lists temperature sensors,
etc.) — Home Assistant does that filtering natively, nothing you need to
set up. They are never asked to type or read out a raw entity ID like
`switch.shellyplug_s_a1b2c3`. The only real task here is figuring out
*which* item in that list is theirs, before or when they reach it — ask
plainly which of the tiers below they want, rather than picking one for
them:

1. **"I already know which is which"** — skip straight to §4; they'll
   recognize their own devices in the dropdown by name.
2. **"I'm not sure — help me find them"** — the easiest no-typing option:
   have them go to **Settings → Devices & Services → Entities**, type a
   keyword into the search box (`valve`, `pump`, `rain`, `temperature`),
   and either read you back what shows up or take a screenshot and paste
   it — you can read a screenshot's entity names directly.
3. **"I want one list of everything relevant, in one go"** — the
   Developer Tools → Template method below. More setup (one extra click),
   but surfaces all of it at once instead of five separate searches.
   ⚠️ **Common snag:** if they don't see **Developer Tools** in their
   sidebar at all, it's hidden behind **Advanced Mode** — tell them to
   click their name/profile (bottom-left corner), scroll down, and turn on
   **Advanced Mode**, then Developer Tools appears in the sidebar.

If they pick option 3, have them open **Developer Tools → Template**,
paste the block below into the left-hand editor, and read back (or
screenshot) what appears on the right — it lists every switch, every
temperature/power sensor, every counter, weather entity, and notify
target, each with its friendly name next to the entity ID so they can
recognize their own hardware instead of decoding cryptic IDs.

**Say this plainly before they run it:** this list can reveal more about
their home than just irrigation — device names, room layout, other
people's names if a notify target or entity is named after them, and so
on. It's fine to paste into this private conversation, same as anything
else discussed here, but **it should never be pasted into a public place**
— a public forum post, a public GitHub issue, a public chat channel. If
they only want to hand over less, option 2 (search by keyword) surfaces
just the one entity type at a time instead of everything at once.

```jinja2
=== Switches (candidate valve) ===
{% for s in states.switch -%}
{{ s.entity_id }} — {{ s.name }}
{% endfor %}

=== Temperature sensors ===
{% for s in states.sensor if s.attributes.device_class == 'temperature' -%}
{{ s.entity_id }} — {{ s.name }} ({{ s.state }}{{ s.attributes.unit_of_measurement }})
{% endfor %}

=== Power sensors (candidate pump-power) ===
{% for s in states.sensor if s.attributes.device_class == 'power' -%}
{{ s.entity_id }} — {{ s.name }} ({{ s.state }}{{ s.attributes.unit_of_measurement }})
{% endfor %}

=== Counters (candidate rain gauge) ===
{% for s in states.counter -%}
{{ s.entity_id }} — {{ s.name }} ({{ s.state }})
{% endfor %}

=== Sensors mentioning "rain" (candidate rain gauge, if not a counter) ===
{% for s in states.sensor if 'rain' in s.entity_id or 'rain' in s.name.lower() -%}
{{ s.entity_id }} — {{ s.name }} ({{ s.state }})
{% endfor %}

=== Weather entities ===
{% for s in states.weather -%}
{{ s.entity_id }} — {{ s.name }}
{% endfor %}

=== Notify targets ===
{% for s in states.notify -%}
{{ s.entity_id }} — {{ s.name }}
{% endfor %}
```

If they mentioned they've already organized their devices into an **Area**
(e.g. "Garden", "Backyard") in Home Assistant, offer the shorter,
area-scoped version instead — much less to scroll through:

```jinja2
{% set area = "Garden" %}
{% for e in area_entities(area) -%}
{{ e }} — {{ state_attr(e, 'friendly_name') or e }}
{% endfor %}
```

(Replace `"Garden"` with their actual area name before handing it over.)

Whichever tier they pick, if at any point they say they can't find
something or aren't sure what they're looking at, fall back to the
screenshot option from the very top of this guide — it works for any
screen, not just this step.

## 4. Walk through the config flow

In Home Assistant: **Settings → Devices & Services → Add Integration →
"ZoneFlow Irrigation"**. It's two screens:

**Screen 1 — zone name.** One field, `Zone name`: a short, human name (e.g.
"Front Lawn", "Avocado Tree", "Herb Bed"). This becomes the device name in
the HA UI and the default CSV log filename, so it must be distinct from any
other zone's name.

**Screen 2 — entities, site description, and schedule.** Fields, in the
order they appear:

| Field | What it is | How to fill it in |
|---|---|---|
| Valve switch | the `switch.*` from §3 | required — the only truly required entity |
| Pump power sensor (optional) | the `sensor.*` from §3 | fill in if they have one (§2); leave blank otherwise — see §2's table for what's lost |
| Shared pump ID (optional) | a short label, not an entity — e.g. "Pump A" | leave blank for a single zone or a zone on its own dedicated pump; for a second-or-later zone, see §7.2's pump-grouping question first — set the identical label on every zone that's genuinely on the same physical pump |
| Rain gauge tip counter (optional) | the `counter.*`/`sensor.*` from §3 | fill in if they have one; leave blank otherwise |
| Outdoor temperature sensor (optional) | the `sensor.*` from §3 | fill in if they have one; leave blank otherwise |
| Flow meter (optional) | the cumulative-volume `sensor.*` from §3 | fill in if they have one; leave blank otherwise |
| Phone notify target | a `notify.*` entity | use whatever they answered in §1 — fill it in if they wanted alerts, leave blank if they didn't |
| Weather forecast source | a `weather.*` entity | use whatever they answered in §1 — fill it in if they wanted the forecast gate (§7.4), leave blank if they didn't; can also be added later via the integration's Options if they change their mind |
| Soil type | a dropdown (not sure / sandy / sandy loam / loam / clay loam / clay) | see §5's soil-type guidance below — inform this from the squeeze test if they don't already know, don't just default to "not sure" |
| Drainage | a dropdown (not sure / fast / medium / slow) | usually falls straight out of the soil-type answer — sandy≈fast, loam≈medium, clay≈slow — ask separately only if they describe unusual site drainage (e.g. a raised bed, or a low spot that pools) |
| Slope | a dropdown (flat / slight / moderate / steep) | whatever they answered in §1 |
| Irrigation method | a dropdown (drip / micro-sprinkler / sprinkler / soaker hose / other) | ask directly — this is about their physical hardware, not something to infer |
| Growth-stage auto-ramp | a dropdown (off / fast-growing annual / slow fruiting crop / establishing perennial) | **default is off** — only turn this on if the person opts in; see §6 before offering it |
| CSV log file path | a file path | accept the pre-filled default (`/config/zoneflow_<zone-name-slug>.csv`) unless the person has a reason to change it |
| Enable the deep soak cycle | on/off toggle | **default is on** (this cycle predates the toggle, so on is what every existing zone already does) — but don't just accept the default silently for a *new* zone; see §6a first and actually recommend on/off based on the crop. This same setting also shows up as a real `switch.<zone>_deep_soak_enabled` entity on the zone's dashboard/device page once created (see §6a) — either one flips the identical underlying value, so mention both so the person knows they can toggle it later straight from the dashboard without touching this config flow or the integration's Options again |
| Deep soak schedule time | `HH:MM:SS` | irrelevant if deep soak is disabled above; otherwise default `05:00:00` is reasonable for most climates (before sunrise, before daytime evaporation); ask if they have a strong preference |
| Routine irrigation schedule time | `HH:MM:SS` | default `05:30:00`, same reasoning |
| Deep soak trigger | Fixed time / before or after sunrise / before or after sunset | leave as "Fixed time" unless they specifically want sunrise/sunset-relative scheduling (§7.3) |
| Deep soak sun offset (minutes) | only relevant if the above isn't "Fixed time" | ask how many minutes before/after |
| Routine trigger | same options as deep soak trigger | same guidance |
| Routine sun offset (minutes) | only relevant if routine trigger isn't "Fixed time" | ask how many minutes before/after |

The four descriptive site fields (soil type, drainage, slope, irrigation
method) are **informational only** — nothing in ZoneFlow's scheduling logic
reads them directly. Their entire job is to inform how *you* fill in §5's
real tunable numbers (split-cycle pulse counts, dry-down holdoffs, rain
efficiency); they always have a valid value (even "not sure"/"flat"/"drip"
as defaults), so they never block submitting this screen. Say this plainly
if the person asks why an "unknown" answer is fine here.

Submitting this screen creates the zone. It starts running on the schedule
immediately, with every tunable number still at its factory default until
you set it in §5 — treat the gap between "zone created" and "§5 and §8
both actually finished" as a real window you should close as fast as
possible, not just something to be quick about:

- **Immediately after creating the zone** (before anything else — before
  §4a, before §5), go to this zone's device page → **⋮ → Disable** on the
  config entry. Disabling unloads the integration for this entry, which
  tears down its schedule timers along with everything else — the zone is
  now genuinely inert, not just "running with defaults and hopefully
  finished in time." Tell the person plainly that you're doing this and
  why. Re-enable it (same menu → **Enable**, then reload if prompted) only
  once §5's numbers are set and §8's test pulse has passed. If the
  conversation gets interrupted for any reason while the entry is
  disabled, nothing runs — that's the point.
- **If for some reason you skip disabling it** (Mode B and the person
  would rather not click through that right now, say), say plainly that
  the zone is live with default numbers and, if a temperature/rain sensor
  isn't yet configured, may run on a schedule that doesn't fit this
  specific plant. It's still worth naming what's *not* at risk regardless:
  the stuck-valve and power-loss watchdogs are unconditional Python logic
  in the integration itself, not dependent on this conversation finishing
  — the worst case with default numbers is "waters on a generic schedule
  for a generic duration," never a valve stuck open or a runaway cycle.

**If they asked for a dashboard card in §1:** this is the moment to note
this zone's real entity IDs, while you're already looking at its device
page for §4a and §5 anyway — don't wait until everything else is finished.
If you have HA tool access, list this zone's device's entities now (by
device name, or filtering `number.*`/`sensor.*`/`binary_sensor.*`/
`button.*`/`datetime.*`/`switch.*` for the zone's slug — the deep-soak
on/off switch, §6a, is a `switch.*` entity too) and keep the list. In Mode B,
ask the person to open the zone's device page (**Settings → Devices &
Services → [zone name]**) and read you every entity ID shown there, once,
while they're already on that screen for §4a/§5 — not as a separate ask
later. Either way, hold onto this list; §9 uses it directly instead of
looking anything up again.

### 4a. Seed the zone's history if it isn't actually brand-new

**Never assume Home Assistant already has this history, and never phrase
the question as if you're going to go check for it.** A ZoneFlow config
entry is brand new the moment it's created — its `datetime` entities always
start at "unknown," regardless of how long the actual plant has existed or
how it was watered before today. There is nothing to look up here; the
person is the only source for this, every time.

Ask this before moving on, every time, as two explicit questions (not one
vague one):

1. **"Is this plant/zone genuinely brand new — never watered on any regular
   basis before today — or has it already been getting watered some other
   way (by hand, a different system, or just rain)?"**
2. **If it's been watered before:** "Roughly when did it last get a normal
   watering, when did it last get a deep/thorough soaking (if that's ever
   applied separately), and when did it last actually rain enough to
   matter?" Exact dates are great if they know them; "about a week ago" or
   "early this month" is completely fine too — approximate beats blank.

A newly-created zone left with all three unset looks overdue by default —
it will run its first routine/deep-soak cycle at the very next scheduled
time, whether or not the plant actually needs it yet. That's correct
behavior for a genuinely new planting (question 1 answered "brand new"),
but wrong for someone migrating an already-established plant onto ZoneFlow
(question 1 answered "already watered some other way" — the more common
case in practice), so don't skip asking just because the plant has existed
for a while — the plant's age and the *zone's* watering history are two
different things, and only the second one matters here.

Once you have an answer, set the zone's `datetime` entities (found the same
place as the number entities — the zone's device page, or
`datetime.<zone_name_slug>_*` in Developer Tools → States) accordingly:

- **Last Routine Irrigation** — when it last got its normal/frequent watering
- **Last Deep Soak** — when it last got a deep, thorough watering (skip if
  deep soak is disabled for this zone — see §6a)
- **Last Significant Rain** — when it last actually rained enough to matter
  (not just a drizzle)
- **Planting / Transplant Date** — set this one separately in §6, as part of
  turning on growth-stage auto-ramp, not here — it answers a different
  question (when did the plant's life start) than the three above (when did
  ZoneFlow-relevant watering last happen).

Setting these via the `datetime.set_value` service (or the UI date/time
picker) immediately changes the gating math — e.g. seeding "Last Deep Soak"
to today correctly makes the zone *not* due for another ~14 days. Leave any
of these unset ("unknown") if the person genuinely doesn't know or it
really hasn't happened yet; that's the honest default and gates behave as
if it's simply never occurred (for the growth ramp specifically: leaving
planting date unset while the ramp is "on" is safe by design — it just
means the full weekly target applies until a date is set, never a reduced
one).

## 5. Set the tunable numbers for this zone/crop

**Before suggesting any values, make sure you have four things: what's
being watered (the crop/plant type), roughly where in the world this is,
what kind of soil it's planted in, and the site description already
collected in §4 (drainage, slope, irrigation method).** Assume the person
may know nothing about gardening or irrigation — don't assume they'll know
these terms or why you're asking; a short explanation of *why* each answer
matters is worth the extra sentence.

**Climate.** The same crop genuinely wants different weekly targets and
temperature thresholds depending on climate — use this together with the
crop table below, not in isolation:

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
  season, but watch the forecast dry-spell override (§7.4) — long genuine
  dry spells are normal here, not a sign the forecast gate is misbehaving.

**Soil type, drainage and slope.** These were already collected as
descriptive fields in §4 — this is where that context actually gets used,
translated into real numbers. Most people don't know their soil type off
the top of their head, so if the §4 answer was "not sure," describe this
simple test rather than assuming they'll guess right: *take a handful of
moist (not soaking) soil and squeeze it — if it falls apart immediately,
it's sandy; if it holds a ball shape but crumbles with a poke, it's loam;
if it holds a shape and can be rolled into a ribbon between your fingers,
it's clay.* If they can now answer it, go back and update the §4 field too
— it's a two-second edit via the integration's **Options**, and keeps the
descriptive field honest.

- **Sandy soil / fast drainage:** absorbs even heavy rain well (little
  runoff) but dries out again quickly. Rain efficiency can stay near the
  factory defaults; **shorten the dry-down holdoffs** (both routine and
  deep soak) versus what you'd otherwise pick from root depth alone. For
  split-cycle pulsing (below), sandy soil rarely needs more than 1-2
  pulses with a short or zero soak gap — infiltration isn't the
  bottleneck.
- **Loam / medium drainage:** the "average" case the factory defaults were
  tuned around — no adjustment needed unless something else about the site
  is unusual. 2-3 pulses with a moderate soak gap (15-20min) is a
  reasonable split-cycle starting point.
- **Clay soil / slow drainage:** a heavy downpour runs off rather than
  soaking in, so heavy rain should get *less* credit than the factory
  default assumes — lower `rain_eff_high` (heavy rain efficiency, default
  1.0) toward 0.6-0.7. Clay holds moisture much longer once it does soak
  in, so it's fine to **lengthen the dry-down holdoffs** versus what root
  depth alone would suggest. For split-cycle pulsing, clay is where it
  matters most: use **more, shorter pulses with a longer soak gap between
  them** (e.g. 3-4 pulses, 25-35min rest) so water has time to actually
  infiltrate instead of pooling or running off between pulses.
- **Slope** compounds whichever of the above applies rather than replacing
  it: a sloped clay/slow-drainage site is the case that benefits most from
  more/shorter pulses and a longer soak, since runoff on a slope happens
  faster than on flat ground; a sloped sandy/fast-drainage site is less
  affected, since it absorbs water quickly enough that runoff is less of a
  concern even on a slope. Steep + slow-draining is the strongest signal
  to lean toward the high end of both pulse count and soak-gap length.

**Root depth (deep soak target depth).** Suggest a starting number
yourself first, rather than asking the person to name a depth in
millimeters out of nowhere — most people, even fairly experienced
gardeners, don't have this memorized. Base your suggestion on the crop,
their region, and the soil type already gathered above (root systems
generally reach deeper in well-drained soil and stay shallower in dense
clay; established trees and deep-rooted crops want more depth than
shallow-rooted ones). State the number and your reasoning in one sentence,
then explicitly invite them to override it if they know better — some
people genuinely do have more precise knowledge of their own plant's root
system than a general suggestion can capture, and that input should always
win over the default:

> "For [crop] in [region]'s [soil type] soil, established roots typically
> reach around [X]mm — I'll start the deep soak target there. Let me know
> if you know your plant's actual root depth better than that."

Never *ask* "how deep are your plant's roots?" as an open question first —
that puts the burden on someone who likely can't answer it, when a
reasoned suggestion they can simply accept or correct is far more useful.

**Growth stage.** A plant's water needs aren't flat over its life —
they generally climb as it grows, and peak around flowering/fruit-set for
fruiting crops (pumpkins, strawberries, tomatoes, etc.). If the planting is
a young seedling or was just transplanted, **start at the low end of the
crop range** rather than the number you'd pick for a mature plant of that
type, and say plainly that this is a starting point the person should
revisit upward once the plant is established or starts flowering/fruiting
— unless they turned on growth-stage auto-ramp in §4/§6, in which case say
so instead: the ramp handles that gradual climb automatically from
whatever weekly target you set here, so there's no manual revisiting to
remember. Either way, this is also exactly the moment to ask §6's growth-
stage question if you haven't already — don't leave it implicit or assume
"just planted" by default.

These are starting points to reason from, not a lookup table to follow
blindly — say so if asked, and adjust based on anything more specific the
person tells you about their actual local conditions (a very hot
microclimate, unusually high humidity reducing evaporation, heavy mulching
that cuts evaporation significantly and can justify a lower weekly target,
etc.) rather than climate/soil alone.

One thing worth stating plainly to a first-time user: ZoneFlow drives
**drip or valve** irrigation, not overhead sprinklers, so the usual advice
about watering in the morning to avoid overnight wet foliage (a fungal-
disease concern with sprinklers) doesn't apply to a drip/soaker setup —
drip keeps foliage dry regardless of timing. If they picked micro-sprinkler
or sprinkler as the irrigation method in §4, that concern *does* apply, and
the 05:00/05:30 default schedule is doing double duty for them (minimizing
both evaporation loss and overnight leaf-wetness time); for drip/soaker
hose, it's purely about minimizing evaporation loss before the day heats up.

Also worth setting expectations on: the **deep soak** cycle is a
deep-root strategy — it matters most for plants that actually send roots
down (trees, established shrubs, tomatoes). For genuinely **shallow-rooted
crops** (strawberries, lettuce, most leafy greens, herbs), deep soak is a
minor lever at best — keep its depth modest (see the table below) and
tell the person nearly all of their real watering strategy for those crops
comes from the routine cycle's weekly target, not from leaning on deep
soak.

**Flow rate calibration — ask this directly, don't let it slide by as just
another table row.** This is the one number the whole runtime calculation
is built on (`runtime = needed_mm / flow_rate_mm_per_min`), and it's the
one you must never guess. Ask outright: "do you know your drip/sprinkler
system's actual flow rate?" If yes, use it. If not, walk them through
measuring it now rather than leaving the factory default in place and
moving on: run `zoneflow.test_pulse` for a known number of minutes, then
either read the flow meter's delta (if one is configured) or have them
measure the water depth/volume actually delivered, and divide. Only fall
back to a generic assumption for the irrigation method (e.g. a typical
drip-emitter or sprinkler flow rate) as a temporary placeholder if they
genuinely can't measure it right now, and say plainly that it's a
placeholder that should be replaced with a real measurement when they can.

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
| `..._hot_weather_temp_threshold` (°C) | 3-day avg peak temp that counts as "hot" | local climate — ask, or use ~31°C in the tropics, ~28°C in temperate zones; **only meaningful if an outdoor temperature sensor is configured** — otherwise every cycle uses the normal tier regardless of this number, so don't spend much time tuning it for a zone with no temp sensor |
| `..._cool_weather_temp_threshold` (°C) | 3-day avg peak temp that counts as "cool" | local climate — usually 5-8°C below the hot threshold; same caveat as above if there's no temp sensor |
| `..._emitter_flow_rate_calibration` (mm/min) | **critical** — how fast the emitters actually apply water | ask the person for their drip/sprinkler flow rate, or help them calculate it: run `zoneflow.test_pulse` for a known number of minutes, measure water depth/volume delivered (or read the flow meter's delta, if configured), divide. Do not guess this one; a wrong value makes every runtime calculation wrong. |
| `..._rain_gauge_mm_per_tip_calibration` (mm) | **only relevant if a rain gauge is configured** — how much rainfall one tip of the bucket represents, which the whole rain-aware gate is built on | see §2a — ask if they already know it; if not, look up the gauge's model spec as a starting point, or offer the pour-and-count measurement for a precise value. Skip this row entirely for a zone with no rain gauge. |
| `..._deep_soak_target_depth` (mm) | depth for the infrequent deep-soak cycle | **irrelevant if deep soak is disabled (§6a)** — otherwise see "Root depth" above, suggest first from crop/region/soil, let the person override |
| `..._routine_pulse_count_split_cycle` / `..._routine_soak_interval_between_pulses` (split-cycle for routine) | how many on/soak/on pulses a routine cycle breaks into, and the soak gap between them | soil-driven — see the soil-type guidance above (more/longer-soak for clay, fewer/shorter for sand); factory default (3 pulses, 20min rest) is a loam-tuned middle ground |
| `..._deep_soak_pulse_count_split_cycle` / `..._deep_soak_soak_interval_between_pulses` (split-cycle for deep soak) | same, for the deep-soak cycle | **irrelevant if deep soak is disabled (§6a)** — otherwise same soil-driven guidance; deep soak's larger total depth often benefits from leaning slightly higher on pulse count for clay than the routine cycle does |
| `..._deep_soak_max_safety_runtime_cap` / `..._routine_max_safety_runtime_cap` (min) | hard abort ceiling for a single cycle — if the calculated runtime exceeds this, that cycle is aborted rather than run, since it usually means a miscalibration | **check this for very low-flow drip emitters** (below roughly 0.1mm/min): the calculated runtime for a full target can genuinely run into several hundred minutes, and the factory default caps (124min / 103min) will wrongly abort a perfectly correct, just-slow cycle. Raise the cap (up to 900min) to comfortably cover `target_mm / flow_rate_mm_per_min` for this zone's real numbers — don't just raise it blindly to max "to be safe," since its whole job is catching a genuine miscalibration. The deep-soak cap is moot if deep soak is disabled (§6a). |
| `..._max_daily_irrigation_runtime_safety_cap` (min) | hard ceiling on TOTAL runtime across both cycles in a rolling day — catches a mis-set schedule firing more often than intended, separate from the per-cycle caps above | factory default (240min) is generous; only worth lowering for a genuinely water-restricted setup, and worth checking it comfortably covers deep soak + routine's realistic combined runtime for this zone before lowering it |
| `..._pump_low_power_warning_threshold` (W) | pump-power audit floor | **only relevant if a pump-power sensor is configured** — ask for the pump's rated running wattage, set ~20-30% below it; skip this row entirely for a zone with no pump-power sensor |
| `..._routine_dry_down_holdoff` (days) | holdoff after significant rain before routine resumes; also the number the **self-tuning** feature (below) nudges automatically | shallow-rooted/thirsty plants: lower (1-2d); drought-tolerant: higher (4-6d). Note this one can drift 0.5d at a time on its own over time based on how the person actually uses the manual/snooze buttons — that's expected, not a bug, and they can always move it back by hand |
| `..._deep_soak_subsoil_dry_down_holdoff` (days) | same, for deep soak | **irrelevant if deep soak is disabled (§6a)** — otherwise usually higher than the routine holdoff, since trees/deep roots hold subsoil moisture longer |
| `..._deep_soak_interval_days` (days, default 14) | how many days between deep-soak cycles | shallow-rooted/frequent-deep-soak crops: lower (7-10d); deep-rooted trees needing infrequent deep watering: higher (18-30d). Same category as the target depth above — suggest from crop/root-depth reasoning, let the person override |
| `..._pump_preamble_warm_up_delay` (s) / `..._pump_postamble_settle_delay` (s) | only relevant if this zone shares a pump with another zone (§7.2) | leave at 0 for a single-zone/independent-pump setup |
| `..._forecast_rain_skip_threshold` (mm) / `..._forecast_rain_probability_threshold` (%) / `..._forecast_dry_spell_override` (days) | only relevant if a weather entity was set (§7.4) | see §7.4 |
| `..._soil_moisture_dry_threshold` (%) / `..._soil_moisture_wet_threshold` (%) | only relevant if a soil-moisture sensor was set (§7.7) | see §7.7 |
| `..._crop_factor_kc` | how much water this plant uses relative to reference ET₀ | only read when the zone's **Water Demand Model** is set to the ET curve — see §7.8; leave at the 0.8 default otherwise |

**Quick weekly-water-target starting points by crop type** (mm/week, normal
weather — adjust from here rather than treating these as exact):
- Lawn / turf: 25-35mm
- Vegetable beds, herbs (shallow roots, frequent light watering preferred): 20-30mm, and prefer a lower routine interval logic — this integration adapts the interval automatically via temperature, so you mainly need the weekly target right
- Established trees / avocado / fruit trees: 25-45mm routine **plus** rely on the deep-soak cycle (20-30mm depth) for root-zone penetration
- Succulents / drought-tolerant natives: 10-20mm, and set the dry-down holdoffs and forecast dry-spell override (if used) higher

These are reasonable starting points, not agronomy guarantees — say so if
the person asks, and suggest they watch the diagnostic sensors (§8) for the
first couple of weeks and adjust the weekly target up/down from there —
and tell them what to watch on the plants themselves (§7.9).

## 6. Growth-stage auto-ramp (optional, off by default)

Only bring this up as an offer, not a default — most first-time setups are
fine leaving it off, and it's easy to turn on later via the integration's
Options if the person changes their mind.

**What it does:** scales the routine weekly target (never the deep-soak
depth target — see §5's `deep_soak_target_depth` row for why those are
treated differently) by how many days it's been since the recorded
planting/transplant date, following one of three built-in curves (fast-
growing annual, slow fruiting crop, establishing perennial). A brand-new
seedling gets a fraction of the full target; by the time the curve
reaches its final control point, it gets 100%.

**Be upfront about its real limitation when offering it:** this is a
calendar-day approximation of *typical* growth timing for that category of
plant, not a measurement of this specific plant's actual growth. A cooler
or hotter season than average will make the real plant's growth genuinely
run ahead of or behind the curve — it's tracking averages, not this
particular plant's own progress. Say this plainly rather than letting the
person think it's more precise than it is.

**Also worth saying plainly why it can still be worth turning on despite
that:** a reasonable automatic adjustment that's sometimes a bit off in
either direction is still generally better than a flat weekly target that
never adjusts for the plant's actual life stage at all — some
automatically-adjusted watering beats none, even when the adjustment isn't
perfect. Frame it to the person as "set it and forget it, revisit only if
you notice something looks off" rather than something that needs regular
attention once it's on.

**If they want it:**
1. Set the "Growth-stage auto-ramp" field in §4 to whichever profile best
   matches the crop — fast-growing annual (most vegetables), slow fruiting
   crop (tomatoes, peppers, strawberries, pumpkins), or establishing
   perennial (a young tree or shrub still becoming established).
2. **Ask what stage the plant is at right now, as its own explicit
   question — never assume "just planted" and never fold this into the
   "do you want the ramp" question above.** Two ways they might answer,
   handle both:
   - **They know the actual planting/transplant date** — set the "Planting
     / Transplant Date" datetime entity (§4a) to that real date directly.
   - **They don't know the exact date, but can describe the current stage**
     (e.g. "just a seedling," "growing well but no flowers yet," "already
     flowering/fruiting," "fully mature") — back-calculate an approximate
     planting date instead of leaving this unanswered: look at the chosen
     profile's curve control points (`GROWTH_RAMP_CURVES` in `const.py` —
     e.g. slow-fruiting is roughly 0d=just-planted, ~45d=vegetative
     growth, ~70-100d=flowering/fruiting/mature), pick the days-ago figure
     that matches the stage they described, and set the planting date to
     today minus that many days. Say plainly that this is a backdated
     approximation standing in for a date they don't know, not a guess
     you're hiding.
3. Tell them the ramp fraction is visible on the zone's "Growth Stage Ramp"
   diagnostic sensor (§8) if they want to sanity-check it's doing something
   sensible.

If the profile is on but the planting date is left unset, the ramp simply
never reduces watering (always 100%) until a date is set — this is
intentional, not a bug to work around.

## 6a. Should this zone even run deep soak?

The deep soak cycle is **on by default** (the "Enable the deep soak cycle"
toggle in §4) because it predates that toggle — every zone created before
this field existed already ran it, so "on" is the only default that doesn't
silently change an existing zone's behavior. That default is about
backward compatibility, not a recommendation — for a **new** zone, actually
work out whether this crop/setup benefits from it rather than leaving the
toggle untouched:

**Lean toward turning it off for:** shallow-rooted crops (lettuce, most
leafy greens, herbs, strawberries), anything in a container or small raised
bed (there's no deep subsoil reservoir to fill), and greenhouse/indoor
zones already on frequent drip irrigation where an infrequent deep,
thorough watering doesn't match how the growing medium behaves. For these,
nearly all of the real watering strategy already comes from the routine
cycle's weekly target (§5) — nothing meaningful is lost by leaving deep
soak off, and it removes several irrelevant number entities' worth of
tuning (§5's table already flags each one that stops mattering here).

**Lean toward keeping it on for:** trees, established shrubs, and other
genuinely deep-rooted plants in real ground — anything where infrequent,
thorough soaking actually reaches and encourages deeper root growth versus
frequent shallow watering keeping roots shallow.

**Use your crop research from §1, not just this quick split** — if you
looked up the specific plant's typical root system when you first learned
what's being grown, that's exactly what settles this question for
in-between cases. State your recommendation and reasoning in one or two
sentences and let the person confirm or override it, the same pattern as
root depth in §5 — don't just silently apply your own judgment call.

**Whatever you set it to now isn't final, and doesn't require coming back
through this guide (or the integration's Options) to change later.** Once
the zone exists, this same setting is also a real dashboard entity —
`switch.<zone>_deep_soak_enabled` — right alongside the zone's other
controls (§9's dashboard card includes it). Tell the person about this
switch explicitly: it's there specifically so they can turn deep soak on or
off themselves, on the fly, without needing an AI assistant or a trip
through Settings → the integration's Options every time they want to flip
it. Both the config-flow field, the Options-flow field, and the dashboard
switch are the exact same underlying value — whichever one they use last
wins, and the other two immediately reflect the change.

## 7. Situational features — ask only if relevant

### 7.1 Multiple zones
If the person has more than one plant/area to water, repeat §3-§5 for each
zone (Add Integration → ZoneFlow Irrigation again, with a different zone
name and its own entities). **The moment you're on zone 2 or later, ask the
pump-grouping question below (§7.2) before finishing that zone's config
flow** — don't treat pump sharing as an afterthought to circle back to
later, since it changes a real field on screen 2 of the flow (§4's "Shared
pump ID").

### 7.2 Shared pump
**Ask this explicitly for every zone from the second one onward — never
infer it from whether a pump-power sensor happens to be configured.**
Something like: *"Does this zone share a physical pump with any of the
other zone(s) you've already set up, or does it have its own dedicated
pump?"* For three or more zones, don't stop at a yes/no per zone — work out
the **full grouping** explicitly, the same way you'd ask about a multi-pump
property: "so to confirm — Zone A and Zone B are on the same pump, and Zone
C is on a separate, different pump, is that right?" Get that full picture
before moving on, since a partial answer (confirming just one pair) can
leave a third zone's grouping ambiguous.

Once you know the grouping, set the **same "Shared pump ID"** (config flow
field, or the integration's Options for a zone already created) on every
zone that's genuinely on the same physical pump — a short label the person
picks, like "Pump A" or "Well Pump," doesn't need to match anything else in
their system, it just has to be identical across the zones that share that
pump. Leave it blank for a zone with its own dedicated pump, or when there's
only one zone total. **This is independent of whether a pump-power sensor
is configured** — ZoneFlow used to only detect sharing when two zones
happened to point at the exact same pump-power sensor entity, which silently
missed sharing when that sensor wasn't set (or wasn't set on both), and
could even wrongly force two genuinely separate, sensorless pumps to
serialize. The "Shared pump ID" field is the deliberate, explicit way to
tell ZoneFlow the real grouping regardless of what sensors happen to be
configured — always ask for it rather than relying on the pump-power sensor
alone to imply sharing.

**Zones with different "Shared pump ID" values (or one set and one blank)
never wait on each other** — including a 3+ zone setup with a mixed
grouping (e.g. Zone A and B share "Pump A," Zone C is on its own "Pump B"):
Zone C runs independently and freely overlaps with A or B, while A and B
still correctly take turns. Only zones sharing the identical "Shared pump
ID" serialize.

If the shared pump needs a moment to build pressure, set
`pump_preamble_seconds` (delay after the pump starts before the valve
opens) and/or `pump_postamble_seconds` (delay after the valve closes before
the next queued zone can start) on the zones that share that pump ID. Ask
the person if their pump has a noticeable spin-up/pressure-settle time; if
they don't know, leave both at 0 and revisit only if they see flow-rate
inconsistency between zones.

Worth setting expectations on if the person asks how the queuing actually
behaves: a zone holds the shared pump for its **entire** cycle once it
starts, including any soak gaps between split-cycle pulses (§5) — a second
zone waiting on the same pump will not sneak a pulse in during the first
zone's soak gap, even though the pump is technically idle at that moment.
It waits for the whole first cycle to finish. This is deliberate: letting a
second zone borrow a "free" gap risks that zone getting cut off mid-pulse
the moment the first zone reclaims the pump, which is worse than a
predictable wait.

### 7.2a One flow meter shared across multiple zones

A single physical flow meter behaves differently depending on **where**
it's plumbed relative to the zones — ask about its position, don't assume:

- **Positioned on one shared pump's own line** (after that pump, before it
  branches out to that pump's own zones' valves — the same physical spot
  as a shared pump-power sensor): this just works. Point every zone on
  that pump at the same flow meter entity, same as they already share a
  "Shared pump ID" (§7.2). Since those zones already take turns on the
  pump lock, only one of their valves is ever open while the meter is
  being read, so each zone's own "Last Cycle Water Delivered" reading
  comes out correct automatically — no extra configuration needed.
- **Positioned upstream of MULTIPLE independent pumps** (e.g. one
  main-line meter for the whole property, feeding two or three separate
  pump branches that each have their own zones): this is the case worth
  asking about explicitly, because those pumps are otherwise deliberately
  free to run at the same time (§7.2) — if two zones on genuinely
  different pumps both drew through that one meter at once, its single
  running total would have no way to say afterwards which zone's water
  was which, because the water is actually mixed on that shared line, not
  just ambiguously counted. **There's no way to sort this out after the
  fact by checking which valve is open** — that only works if exactly one
  valve downstream of the meter can ever be open at a time, which two
  simultaneous pumps don't guarantee on their own.

  ZoneFlow handles this automatically the moment two zones are pointed at
  the **same flow meter entity**, regardless of their "Shared pump ID":
  it serializes those specific zones' cycles against each other too, the
  same way pump-sharing zones already take turns. Tell the person plainly
  what this costs them: those particular zones lose the "different pumps
  run at the same time" benefit they'd otherwise get, purely because a
  shared meter can't tell their water apart if it doesn't. If they'd
  rather keep their independent pumps running fully concurrently, the
  fix is a separate flow meter per pump (even one meter per pump, shared
  across that pump's own zones, is enough — it's specifically sharing
  *across* pumps that forces the trade-off) — mention this as the
  alternative, but let them decide; plenty of setups are fine giving up a
  little concurrency for one meter's worth of savings.

### 7.3 Sunrise/sunset-relative scheduling
If the person wants watering tied to daylight rather than a fixed clock
time (e.g. "start 30 minutes before sunrise" so it adapts across seasons),
set the relevant trigger field (in §4's table) to one of Before/After
Sunrise/Sunset and fill in the offset in minutes. This is independent per
schedule (deep soak and routine can each use a different mode).

### 7.4 Weather forecast gate
Only set this up if the person wants ZoneFlow to skip a scheduled run when
rain is forecast. Requires a `weather.*` entity (any integration that
provides one — ask which weather integration they use, or find it via §3).

**For a greenhouse/indoor zone, this is governed by the rain-can-enter
question in §2** — always ask it, and default to skipping this gate
(along with the rain gauge) unless the person confirms real rain reaches
the zone. A forecast of rain outside is irrelevant to plants that never
get rained on. If you're setting up multiple zones and only some are
greenhouses, this is genuinely per-zone: an outdoor zone using the same
`weather.*` entity is completely normal, you just don't offer or apply
the gate to a sealed greenhouse zone.

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

### 7.5 One zone, two different crops
If a single valve/zone actually waters two different crops planted
together (a shared bed, a mixed container, two things sharing one drip
line) and the person wants ZoneFlow to treat it as one zone rather than
splitting it into two, don't just pick one crop's numbers and quietly
drop the other — the whole point of asking about crop type in §1 is to
get the right target for what's actually planted, and picking only one
plant silently waters the other wrong for as long as the zone exists.

Instead, help the person find a compromise that reasonably satisfies
both:
1. Work out what each crop would want on its own — its weekly target
   range, hot/cool temp thresholds, and (if relevant) deep-soak posture —
   using the same reasoning §5/§6a would apply if it were its own zone.
2. Where the two crops' numbers are close, just pick a value that covers
   both (e.g. the higher of two similar weekly targets rarely hurts the
   lower-need crop, especially with decent drainage).
3. Where they genuinely conflict (e.g. one crop wants deep, infrequent
   watering and the other wants frequent, shallow watering — or one is
   drought-tolerant and the other isn't), say so plainly rather than
   averaging blindly: explain the tension in plain terms, propose a
   middle value that leans toward whichever crop is more sensitive to
   under-watering (thirstier/shallower-rooted plants suffer faster from a
   shortfall than a drought-tolerant one suffers from a bit of extra
   water), and let the person make the final call if they'd rather
   prioritize one crop over the other.
4. Note the compromise and the reasoning behind it somewhere the person
   will see again later (e.g. in the zone's name, a comment, or just
   restating it back to them) — a shared-zone compromise is exactly the
   kind of setup decision that's easy to forget the "why" behind months
   later.
5. If the mismatch is too large for any single number to serve both
   crops without real harm to one of them, say that plainly too, and
   suggest splitting into two zones (two valves) as the more correct
   long-term fix — a compromise is for when splitting isn't practical,
   not a substitute for it when the two crops are just too different.

### 7.6 A sensor drops out later (already configured, now unavailable)
Worth mentioning proactively once, rather than waiting for the person to
notice and worry: if an already-configured optional sensor goes
unavailable later (dead battery, a Zigbee dropout, a broken template) —
not "never configured," but "was working, now isn't" — ZoneFlow degrades
the same safe way as if it had never been set, automatically, with no
action needed:
- **Outdoor temperature drops out:** the hot/cool tier logic immediately
  falls back to the normal tier (not whatever tier the last real reading
  implied), and recovers automatically the moment the sensor reports again.
- **Rain gauge drops out:** unreadable readings are simply ignored, not
  recorded as "it stopped raining" — the rolling rain window keeps its last
  good value rather than resetting.
- **Pump-power sensor drops out:** treated the same as a genuine low-power
  reading — it warns (if notifications are on), but the cycle still
  completes; a dead sensor never blocks the actual watering.
- **Flow meter drops out:** the no-flow-detected check is skipped for that
  cycle rather than firing a false alarm — "no data" is never treated as
  "definitely zero flow."
- **Soil moisture sensor drops out (§7.7):** the routine-irrigation decision
  falls back to the plain modeled interval, exactly as if no soil-moisture
  sensor had ever been configured, until it reports a real reading again.
- **Outdoor temperature drops out on a zone using the ET curve (§7.8):**
  that zone's weekly target falls back to the temperature-tier target
  (itself the normal tier while the sensor is dead) for as long as the
  sensor is out, and goes back to the ET curve on its own once it reports
  again. The Routine Weekly Target sensor's `source` attribute reads
  `temperature_tiers_fallback` while this is happening.

Temperatures are always handled in °C internally. If the person's Home
Assistant is set to Fahrenheit, ZoneFlow converts the sensor's readings
automatically — but the threshold numbers themselves (hot/cool
thresholds) are always entered in °C, so convert for them if they think
in °F.

### 7.7 Optional soil-moisture sensor
Only set this up if the person has an actual soil-moisture probe already
installed (this is never something to suggest buying just for ZoneFlow —
it's a pure enhancement on top of the modeled schedule, not a requirement).
Requires a `sensor.*` entity reporting moisture as a percentage.

1. Set the zone's "Soil Moisture Sensor" field to that entity (config flow,
   or later via **Options**).
2. Ask about the two threshold numbers, `..._soil_moisture_dry_threshold`
   (default 20%) and `..._soil_moisture_wet_threshold` (default 60%):
   - Sandy/fast-draining soil dries out at a higher raw percentage than clay
     holding the same practical moisture — if the person knows their
     sensor's typical dry/wet readings for their soil, use those instead of
     the defaults.
   - Shallow-rooted, drought-sensitive plants benefit from a higher dry
     threshold (react to dryness sooner); drought-tolerant/deep-rooted
     plants can tolerate a lower one.
3. Explain the mechanic briefly if asked: this is deliberately **routine-only**,
   not deep soak — a shallow probe measures topsoil moisture, which is
   exactly what the routine cycle targets, but doesn't reflect the
   root-zone depth the deep-soak cycle is aiming for. Below the dry
   threshold, ZoneFlow waters even if the modeled interval isn't due yet;
   above the wet threshold, it skips even if the interval says overdue; in
   between, it defers entirely to the plain modeled schedule, same as
   before this was configured. A dropout degrades the same way (§7.6).

### 7.8 Optional ET curve (evapotranspiration-based weekly target)
By default a zone's routine weekly target comes from three fixed tiers —
cool, normal, hot — picked by the 3-day average peak temperature. Each
zone can instead use a continuous curve: set its **Water Demand Model**
select to **ET curve (Hargreaves)**, and the weekly target becomes

    weekly target = 3-day average reference ET₀ (mm/day) × 7 × crop factor (Kc)

ET₀ comes from the zone's own **Reference ET₀ (3-Day Avg)** sensor
(Hargreaves-Samani, from the daily min and max temperature plus the
latitude set in Home Assistant's own settings, so check that Home
Assistant's home location is roughly right). Only the weekly **target**
changes: the 3-or-4-day interval still follows the hot threshold, and
rain credit, the growth-stage ramp (§6), runtime caps and every other gate
apply exactly as with the tiers.

When to suggest it: someone who wants the target to track the weather
smoothly instead of jumping between three values, and who has a working
outdoor temperature sensor. It's opt-in per zone and changes nothing until
selected. Leave it off for a zone with no temperature sensor — it would
just fall back to the tiers every cycle.

Setting the crop factor (`..._crop_factor_kc`, default 0.8). Don't just
leave the default or pick from memory — work out a real value for this
person's plant and place, the same way §5 reasons about weekly targets:

1. **Ask** (skip anything they already told you in §1): the exact crop,
   and variety if they know it; roughly how old and how big the plant is
   (for a tree, how much of the ground under it the canopy shades);
   where they are and what the climate's like (humid tropics, dry
   Mediterranean summer, temperate, arid); and whether the soil under it
   is bare, mulched, or covered by grass or other plants.
2. **Look it up** if you have web access. Search for the published crop
   coefficient for that crop — FAO Irrigation and Drainage Paper 56
   (Table 12, the "mid-season" value for perennials and the
   full-canopy value for annuals) is the standard reference, and a local
   agricultural extension service or university for their region is
   better still when one publishes figures, since it already reflects
   local conditions. Tell the person the number you found and where it
   came from, in one line.
3. **Adjust it for their situation**, and say why in plain words:
   - Humid climate (the tropics, a humid coastal summer): the Hargreaves
     ET₀ this zone uses tends to read somewhat high there, so go toward
     the low end of the published range.
   - Hot, dry, windy climate: toward the high end.
   - Young or small plant, or a tree shading only part of the ground:
     keep Kc at the grown-plant value and let the growth-stage ramp (§6)
     scale it down, so the number stays right as the plant grows. Only
     lower Kc itself for a plant that will stay small or sparse.
   - Drip on mostly bare or mulched soil (only the root zone is wetted):
     a little lower, typically 0.05-0.1, since less surface evaporation
     happens than the published figures assume.
4. **No web access?** Use the starting points below, say plainly that
   they're general starting points rather than a looked-up value, and
   suggest the person check with a local nursery or extension service.

Starting points for a mature, full-size plant in its main growing season:
- Warm-season lawn: 0.6-0.8; cool-season lawn: 0.8-0.95
- Tomatoes, peppers, pumpkins and other vegetables at full canopy: 1.0-1.15
- Strawberries: 0.85-1.0
- Avocado: 0.75-0.85; citrus: 0.65-0.7; olive: 0.6-0.7
- Cherry and other stone fruit in season: 0.9-1.0
- Succulents / drought-tolerant natives: 0.3-0.5

Whatever you set, it's a starting point, not an agronomy guarantee. Finish
by telling the person what to watch on this specific plant so they know
when to nudge Kc up or down later (§7.9).

What to show them: the zone's **Routine Weekly Target** sensor shows the
target a routine cycle would use right now (including the growth ramp),
and its `source` attribute says which model produced it (`et_curve`,
`temperature_tiers`, or `temperature_tiers_fallback`). The ET₀ sensor
reads "unknown" until one full day of min/max temperature has been
recorded, and the zone uses the tiers until then.

### 7.9 Tell the person what to watch on their plants
Every number in this setup — weekly targets (§5) or the crop factor
(§7.8) — is a starting estimate, and the plant itself is the real test.
Before you finish, tell the person in a few plain sentences what to look
for on **their** crop, when to look, and which number to change:

**How to check:**
- Look at the plants in the **early morning**, before the day's heat.
  Many plants (pumpkins, squash, tomatoes) droop in hot afternoon sun even
  when well watered and recover by evening — that's normal. Drooping that
  is still there first thing in the morning means too dry.
- Feel the soil at root depth a day or two after a watering, not just the
  surface: push a finger or a trowel in 5-10 cm for vegetables, 15-20 cm
  for trees. Moist but not soggy is right. Dry at that depth means too
  little water; still wet and cold means too much.
- Give each change a week or two before judging it, and change one thing
  at a time.

**Signs by plant type** (pick the ones for their crop, don't read out the
whole list):
- **Avocado:** very sensitive to waterlogging (root rot) — yellowing
  leaves, dieback, soil that stays wet for days means too much. Wilting
  or drooping new growth and brown, crispy leaf edges mean too little
  (brown tips can also be salt build-up — worth mentioning).
- **Citrus:** leaves curling inward lengthwise = too dry; yellowing
  leaves and leaf drop with damp soil = too wet.
- **Olive:** drought tolerant, so overwatering is the more common
  mistake — yellowing and dropping leaves. Shrivelled fruit while it's
  developing = too dry.
- **Tomatoes:** fruit cracking or splitting after a big watering that
  follows a dry spell, and blossom-end rot (dark sunken patch at the
  bottom of the fruit) both point to watering that's too uneven —
  usually too little between cycles. Yellowing lower leaves with wet
  soil = too much.
- **Chilis / peppers:** flowers dropping before setting fruit in hot, dry
  weather = too dry; yellowing lower leaves and wet soil = too much.
- **Pumpkins / squash / melons:** judge by morning wilting only (see
  above). Small fruit that stops growing = too dry.
- **Strawberries:** shallow roots dry out fast — small, dry or seedy
  fruit and crispy leaf edges = too dry; grey mould on fruit or a soft,
  rotting crown = too wet.
- **Cherry / stone fruit:** fruit splitting near harvest often follows a
  sudden large watering after dry weather — keep watering steady in the
  last weeks before harvest.
- **Lawn:** a blue-grey tint and footprints that stay pressed down = too
  dry; spongy turf, moss or mushrooms = too wet.
- **Succulents / drought-tolerant natives:** wrinkled, shrivelled leaves
  = too dry; soft, mushy or see-through leaves = too wet (the much more
  common problem).
- For any other crop, look up its typical over- and under-watering signs
  the same way you looked up its crop factor, and tell them the two or
  three that matter most.

**What to change:**
- Consistently too dry: raise the zone's **Crop Factor (Kc)** by 0.05 if
  it's on the ET curve, or its routine weekly target(s) by about 10% if
  it's on the temperature tiers.
- Consistently too wet: lower the same number by the same step.
- Suggest they note what they see in the zone's **Health** and **Health
  Notes** fields, so there's a record to look back on the next time
  someone adjusts it.

## 8. Verify before you're done

Do not consider setup finished until these are confirmed for each zone:

1. **If you have Mode A tool access, get an explicit yes before you
   trigger this — never call the service yourself just because the guide
   says to run it.** Tell the person plainly, by name: "This will
   physically open `switch.<their valve>` for 10 seconds — is now a safe
   time to run that?" This is a real, physical action on their actual
   hardware, bypassing every schedule/rain/dry-down gate on purpose, and
   you have no way to know whether someone's mid-repair on the plumbing,
   whether the pump is disconnected, or anything else about the physical
   state of the system right now — only the person on-site knows that. In
   Mode B this step is naturally already gated, since the person is the
   one clicking it.

   Once confirmed, run **Developer Tools → Actions → `zoneflow.test_pulse`**
   with `seconds: 10` (targeting that zone's device, since each zone is its
   own config entry/service target if the person has multiple). Confirm:
   the valve entity actually switches on then off, and a new row appears in
   the configured CSV log file. If a pump-power sensor is configured, also
   confirm it reads a plausible non-zero value while the valve is on. If a
   flow meter is configured, confirm its "Last Cycle Water Delivered"
   sensor picks up a plausible non-zero value after the pulse.
2. Check the zone's diagnostic sensors exist and show sane values: rain
   past 24h/3d/7d/14d (if a rain gauge is configured), 3-day average peak
   temperature (if a temp sensor is configured), Reference ET₀ (normal to
   read "unknown" on day one, see §7.8), Routine Weekly Target (should
   match the zone's normal weekly target unless the ET curve is selected),
   next-irrigation estimate,
   Days Until Next Run, Soil Profile (should reflect what was set in §4),
   and Growth Stage Ramp (only meaningfully non-100% if that feature is on
   — §6). Also confirm the `switch.<zone>_deep_soak_enabled` entity exists
   and its on/off state matches whatever you set/recommended in §6a.
3. Confirm the lock/abort binary sensors both read "off"/`False` at rest —
   if either is stuck on, something is wrong before you hand this back to
   the person unattended (`zoneflow.reset_lock` clears a stuck lock, but
   find out why it was stuck first).
4. Tell the person plainly what will happen next (which zones water at
   which times), and what to watch on each zone's plants over the next
   couple of weeks (§7.9) and remind them the `test_pulse` service bypasses every
   safety/rain gate on purpose, so it's not representative of a real run —
   don't leave them thinking a successful test pulse alone proves the rain
   logic works.
5. **Check whether they said yes to a dashboard card and/or a cheat sheet
   back in §1's item 6.** For whichever one(s) they said yes to, setup is
   *not* finished until §9 and/or §9a are actually done and the person has
   the finished output in hand — not just noted as something you'll get
   to. It's easy to reach this point, confirm the test pulse and sensors
   look good, and declare the job done without circling back to a "cosmetic
   extra" from several steps ago. Don't let that happen: treat a yes on
   either one exactly like any other item on this list — required before
   you say setup is complete, not an afterthought you can skip if it slips
   your mind.

## 9. Optional finishing touch: build a dashboard card for this zone

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
again. **Only include cards/rows for entities that actually exist for this
zone** — a zone with no pump-power sensor configured has no pump-power
entity to reference, and a zone with the growth ramp off still has the
Growth Stage Ramp diagnostic sensor (it just reads 100%), so that one's
always safe to include:

1. Take the entity ID list you collected back in §4. If for some reason you
   skipped that (the person changed their mind about wanting a card only
   after setup was already finished), do it now the same way: HA tool/API
   lookup by device name or by filtering `number.*`, `sensor.*`,
   `binary_sensor.*`, `button.*`, `datetime.*` for the zone's slug, or ask
   the person to read the IDs off **Settings → Devices & Services → their
   zone's device**.
2. Fill the template below with those confirmed IDs — every `<entity.id>`
   placeholder — so what you hand back is genuinely paste-ready, not a
   fill-in-the-blanks exercise for the person. Drop any row whose entity
   doesn't exist for this zone (see above) rather than leaving a
   placeholder unfilled.
3. Tell them exactly where to paste it: **Settings → Dashboards → (their
   dashboard) → ⋮ Edit Dashboard → ⋮ Raw configuration editor**. **Never
   have them select-all and paste over what's already there** — the raw
   editor shows their *entire* dashboard, and overwriting it deletes every
   other view/card they already have. What they should actually do:
   - If they already have a YAML-mode dashboard with a `views:` list, this
     zone's view (the one `- title: ...` block below) gets added as one
     more item in that existing list — inserted right after the last `-`
     entry under `views:`, keeping everything above it untouched. Tell them
     explicitly: "scroll to the end of your `views:` list and add this as a
     new `-` entry, don't replace anything above it."
   - If they don't have a YAML-mode dashboard yet (most first-time users on
     the default auto-generated one don't), point them at **Settings →
     Dashboards → + Add Dashboard → "New dashboard from scratch"** first —
     the auto-generated dashboard can't be hand-edited — and only on that
     brand-new, empty dashboard is pasting the whole template from scratch
     (including the top-level `views:` key) correct.
   - If at any point you're not looking at their actual current YAML (e.g.
     they're describing it to you rather than you reading it via tool
     access), say so and have them paste their existing raw config back to
     you first so you can show the insertion point precisely, rather than
     guessing where their existing views end.

**Give every zone a distinct icon and a visible zone-name heading — never
reuse the same generic icon (e.g. `mdi:sprinkler`) across zones.** With
several zones set up, identical tab icons make the view switcher a row of
lookalikes the person can only tell apart by squinting at small text, and
that defeats the point of splitting zones into separate views at all. For
each zone:
- Pick an icon that fits what's actually planted, not just "it's a zone" —
  a real crop/plant icon (e.g. a chili, a tree, a sprout, a greenhouse for
  an indoor zone) reads at a glance in a way a repeated watering-can icon
  never will. Use whatever fits best; there's no fixed list, but don't
  fall back to one generic icon for every zone just because picking one
  per crop takes an extra moment.
- Put a `heading` card as the **first card in the view**, `heading` set to
  the zone's actual name and `icon` set to that same per-zone icon. This
  makes the zone identifiable the instant the view loads, not just from
  the tab label — useful on a phone where tab labels get cramped, or when
  the person is several cards deep and scrolled past the tab bar.

Template — a complete dashboard document with one `views:` entry per zone,
using only plain built-in cards (no extra HACS frontend dependency
required). **The top-level `views:` key is mandatory** — pasting just a
bare `title:`/`path:`/`cards:` block on its own into the raw configuration
editor fails with `Expected an array value, but received: undefined` at
`views`, because that's not a complete dashboard document by itself:

```yaml
views:
  - title: <Zone Name>
    path: <zone-slug>
    icon: <a distinct per-zone icon, e.g. mdi:chili-hot, mdi:greenhouse, mdi:sprout, mdi:tree>
    cards:
      - type: heading
        heading: <Zone Name>
        heading_style: title
        icon: <same per-zone icon as above>

      - type: entities
        title: Status
        show_header_toggle: false
        entities:
          - entity: <switch.valve_entity>
            name: Valve
          - entity: <binary_sensor.zone_irrigation_in_progress>
            name: Lock (In Progress)
          - entity: <binary_sensor.zone_irrigation_abort_flag>
            name: Abort Flag
          - entity: <sensor.zone_pump_power_entity_if_configured>
            name: Pump Power
          - entity: <sensor.zone_last_cycle_water_delivered_if_flow_meter_configured>
            name: Last Cycle Water Delivered
          - entity: <sensor.zone_next_irrigation_estimate>
            name: Next Run Estimate
          - entity: <sensor.zone_days_until_next_run>
            name: Days Until Next Run

      - type: entities
        title: Manual Controls
        show_header_toggle: false
        entities:
          - entity: <switch.zone_deep_soak_enabled>
            name: Deep Soak Enabled
          - type: buttons
            entities:
              - entity: <button.zone_run_deep_soak_now>
                name: Run Deep Soak
                icon: mdi:waves
              - entity: <button.zone_run_routine_irrigation_now>
                name: Run Routine
                icon: mdi:play
              - entity: <button.zone_reset_irrigation_lock>
                name: Reset Lock
                icon: mdi:lock-open-variant
              - entity: <button.zone_snooze_today>
                name: Snooze Today
                icon: mdi:sleep

      - type: entities
        title: Health Journal
        show_header_toggle: false
        entities:
          - entity: <select.zone_health>
            name: Health
          - entity: <text.zone_health_notes>
            name: Notes
          - entity: <datetime.zone_last_fertilizing>
            name: Last Fertilizing
          - entity: <select.zone_next_fertilizing_in>
            name: Next Fertilizing In

      - type: entities
        title: Site & Growth Profile
        show_header_toggle: false
        entities:
          - entity: <sensor.zone_soil_profile>
          - entity: <sensor.zone_growth_stage_ramp_if_enabled>
          - entity: <datetime.zone_planting_transplant_date_if_enabled>

      - type: entities
        title: Water Demand
        show_header_toggle: false
        entities:
          - entity: <select.zone_water_demand_model>
            name: Water Demand Model
          - entity: <sensor.zone_routine_weekly_target>
            name: Weekly Target (in effect now)
          - entity: <sensor.zone_reference_et0_3_day_avg_if_temp_sensor_configured>
            name: Reference ET0 (3-day avg)
          - entity: <number.zone_crop_factor_kc>
            name: Crop Factor Kc (ET curve only)

      - type: entities
        title: Routine Irrigation
        show_header_toggle: false
        entities:
          - entity: <number.zone_routine_normal_weekly_target>
          - entity: <number.zone_routine_hot_weekly_target>
          - entity: <number.zone_hot_weather_temp_threshold>
          - entity: <number.zone_routine_cool_weekly_target>
          - entity: <number.zone_routine_dry_down_holdoff>
          - entity: <number.zone_routine_pulse_count_split_cycle>
          - entity: <number.zone_routine_soak_interval_between_pulses>

      - type: entities
        title: Soil Moisture (Optional)
        show_header_toggle: false
        entities:
          - entity: <number.zone_soil_moisture_dry_threshold_if_sensor_configured>
            name: Dry Threshold %
          - entity: <number.zone_soil_moisture_wet_threshold_if_sensor_configured>
            name: Wet Threshold %

      - type: entities
        title: Deep Soak
        show_header_toggle: false
        entities:
          - entity: <number.zone_deep_soak_interval>
            name: Interval (Days)
          - entity: <number.zone_deep_soak_target_depth>
          - entity: <number.zone_deep_soak_rain_ceiling_14d>
          - entity: <number.zone_deep_soak_subsoil_dry_down_holdoff>
          - entity: <number.zone_deep_soak_pulse_count_split_cycle>
          - entity: <number.zone_deep_soak_soak_interval_between_pulses>

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
          - entity: <number.zone_rain_gauge_mm_per_tip_calibration_if_configured>
          - entity: <number.zone_pump_low_power_warning_threshold_if_configured>
          - entity: <number.zone_deep_soak_max_safety_runtime_cap>
          - entity: <number.zone_routine_max_safety_runtime_cap>
          - entity: <number.zone_max_daily_irrigation_runtime_safety_cap>

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
          {% set lock = states('<binary_sensor.zone_irrigation_in_progress>') %}
          {% set abort = states('<binary_sensor.zone_irrigation_abort_flag>') %}
          {% set routine_ts = states('<datetime.zone_last_routine_irrigation>') %}
          {% set deep_soak_ts = states('<datetime.zone_last_deep_soak>') %}
          | Field | Value |
          | :--- | :--- |
          | **Lock (In Progress)** | {{ 'RUNNING' if lock == 'on' else 'idle' }} |
          | **Abort Flag** | {{ 'PROBLEM' if abort == 'on' else 'OK' }} |
          {% if routine_ts not in ['unknown', 'unavailable', none] %}
          | **Last Routine Irrigation** | {{ as_timestamp(routine_ts) | timestamp_custom('%b %d, %H:%M') }} |
          {% endif %}
          {% if deep_soak_ts not in ['unknown', 'unavailable', none] %}
          | **Last Deep Soak** | {{ as_timestamp(deep_soak_ts) | timestamp_custom('%b %d, %H:%M') }} |
          {% endif %}
```

**Drop the entire "Deep Soak" card** for a zone that has the deep
soak cycle turned off (§6a) — every entity in it still technically exists,
but none of it does anything meaningful, so including it would just be
confusing clutter rather than a genuinely-existing-but-irrelevant row (the
same "only include what actually applies to this zone" rule as any other
optional entity).

**Drop the "Soil Moisture (Optional)" card** for a zone with no
soil-moisture sensor configured (§7.7), for the same reason. **Keep the
"Water Demand" card for every zone that has an outdoor temperature
sensor**, even if they're staying on the temperature tiers for now — the
Water Demand Model dropdown is how they switch that zone between the old
way and the ET curve later (§7.8), so they shouldn't have to come back and
edit the dashboard just to find that switch. For a zone with no
temperature sensor, drop the Reference ET0 and Crop Factor rows but keep
the Weekly Target row.

If the person has multiple zones, add another entry to the same top-level
`views:` list (one tab per zone) rather than stacking every zone's cards
into a single long page — mirrors how the entities themselves are already
split one config entry per zone. If they're pasting this into raw
configuration alongside views that already exist, add these entries into
their existing `views:` list rather than replacing it wholesale.

**With two or more zones, also add an "All Zones" tab at the end** so they
can switch every zone between the old way and the ET curve in one tap
instead of zone by zone. List every zone's real
`select.<zone>_water_demand_model` entity in both buttons and in the
per-zone list (same confirmed-ID rule as above). The buttons ask for
confirmation first, since they change how every zone waters:

```yaml
  - title: All Zones
    path: all-zones
    icon: mdi:sprinkler-variant
    cards:
      - type: heading
        heading: All Zones
        heading_style: title
        icon: mdi:sprinkler-variant

      - type: horizontal-stack
        cards:
          - type: button
            name: "All zones: old way (temperature tiers)"
            icon: mdi:thermometer-lines
            show_state: false
            tap_action:
              action: perform-action
              perform_action: select.select_option
              target:
                entity_id:
                  - <select.zone1_water_demand_model>
                  - <select.zone2_water_demand_model>
              data:
                option: temperature_tiers
              confirmation:
                text: Switch ALL zones to the temperature tiers (old way)?
          - type: button
            name: "All zones: ET curve"
            icon: mdi:chart-bell-curve
            show_state: false
            tap_action:
              action: perform-action
              perform_action: select.select_option
              target:
                entity_id:
                  - <select.zone1_water_demand_model>
                  - <select.zone2_water_demand_model>
              data:
                option: et_curve
              confirmation:
                text: Switch ALL zones to the ET curve?

      - type: entities
        title: Water Demand Model per zone
        show_header_toggle: false
        entities:
          - entity: <select.zone1_water_demand_model>
            name: <Zone 1 Name>
          - entity: <select.zone2_water_demand_model>
            name: <Zone 2 Name>

      - type: entities
        title: Weekly Target in effect now
        show_header_toggle: false
        entities:
          - entity: <sensor.zone1_routine_weekly_target>
            name: <Zone 1 Name>
          - entity: <sensor.zone2_routine_weekly_target>
            name: <Zone 2 Name>
```

Leave out any zone with no outdoor temperature sensor from the "ET curve"
button's list, since it could only ever fall back to the tiers anyway.
There's deliberately no single on/off toggle for this: zones can be mixed
(some on the ET curve, some not), and one toggle would show the wrong
state whenever they are.

One honest caveat to pass on to the person: this is plain built-in HA
cards, chosen deliberately so nothing extra needs installing. It won't look
as polished as a purpose-built dashboard (gauges, sparklines, a custom
panel) — if they want that, it's a separate, bigger undertaking outside
what this integration ships with.

## 9a. Optional finishing touch: a plain-language cheat sheet

This only applies if the person said yes to it back in §1's item 6 —
independent of the dashboard card above, skip it outright if they only
wanted one or neither. Where §9 is built for looking at, this is built for
*reading*: a short, plain-language reference for anyone who'll interact
with this zone day to day without necessarily knowing (or wanting to know)
what a config entry or a `number` entity is. Write it in the same message
or as a short separate document, whichever the person prefers — no fixed
format is required, but cover:

1. **What this zone does, in one or two sentences** — plain description
   using the crop/zone name they gave you, not ZoneFlow's internal terms
   ("Front Lawn waters automatically every morning, and gets a deeper soak
   every two weeks" beats "runs routine_irrigation and deep_soak on
   independent schedules").
2. **The two or three things a person might actually want to do by hand**,
   each as a literal click-path using the real entity/button names from
   this zone's device page — not the generic service names. For example:
   "To water it right now: go to Settings → Devices & Services →
   [zone name] → click **Run Routine Irrigation** ." Only include
   controls that exist for this zone (skip deep-soak buttons if that
   cycle is disabled per §6a).
3. **What to do if something looks stuck or wrong** — in plain terms: if
   the valve seems to be running forever, or hasn't run in a long time and
   should have, point them at the **Reset Irrigation Lock** button and
   suggest they mention it to whoever set this up (or paste it back to an
   AI) rather than guessing at a fix themselves.
4. **What to watch on the plants** — the two or three signs from §7.9
   that matter for this crop, in one or two sentences ("if the leaves are
   still drooping first thing in the morning, it needs more water — tell
   whoever set this up"). Leave out which number to change; that's for
   whoever tunes it.
5. **Skip anything that requires understanding a number's meaning** to act
   on — weekly water targets, thresholds, calibration numbers, etc. belong
   on the dashboard (§9) or in the full docs, not this cheat sheet. The
   goal here is confident day-to-day use by someone who never opens the
   Options flow, not a tuning reference.

Keep it short — a few sentences and a short list of click-paths, not a
restated version of this whole guide.

## 10. Ground rules while you do this

- **Scope lock (see the non-negotiable at the top) — what this means in
  practice for Mode A:**
  - **Reads are always fine.** Looking up entities, states, existing
    automations, or areas to find candidates (§3) or to write dashboard
    entity IDs correctly (§9/§9a) never touches anything, so there's
    nothing to be cautious about there.
  - **Writes are scoped to exactly what this guide asks you to create**:
    the new ZoneFlow config entry, its options, its number/select/datetime
    values, and — only if requested — new dashboard content or a cheat
    sheet. Never edit, reorder, or remove an existing automation, script,
    helper, entity, or dashboard view as part of this.
  - **Dashboard edits (§9) are additive only.** Add a new `views:` entry;
    never touch an existing view or card that was already there, even if
    it looks related or you think it could be improved to match.
  - **Don't comment on unrelated parts of their setup unprompted** — not a
    naming convention you'd do differently, not an automation that looks
    inefficient, not an entity that looks misconfigured for something
    else entirely. If it's not blocking this specific setup, it's not
    your concern right now. The one exception: something you notice that
    looks like a genuine problem is worth mentioning once, plainly, then
    dropping — never acting on it without being asked.
- Never guess an entity ID and submit it without the person confirming it —
  a confident tool-based lookup earns you a good candidate to propose, not
  a substitute for the person actually confirming it. This is unconditional
  (§3 already says the same thing; this isn't a looser restatement of it).
- Never disable or bypass a safety watchdog (stuck-valve force-off,
  power-loss abort, stale-lock recovery) — these aren't configurable by
  design, and that's intentional; don't suggest workarounds.
- Don't touch `custom_components/zoneflow/calculations.py` or any other
  integration source file as part of "setup" — setup is entity selection +
  number tuning through the UI, never a code change.
- If something doesn't fit this guide (an entity type you can't find, a
  request to change scheduling logic itself, an error message not covered
  here), say so plainly, and offer to draft a GitHub issue for it rather
  than improvising a change to how the integration behaves.

### 10.1 Drafting a GitHub issue — privacy comes first

If the person wants you to open (or draft the text for) a GitHub issue —
a bug report, a feature request, anything that will end up on a **public**
repository — treat this as sensitive by default, not as "just copy what
happened." Home Assistant setups routinely contain things that must never
end up in a public issue tracker. Before showing the person a draft:

- **Strip, don't just paraphrase:** never include access tokens, API keys,
  or credentials of any kind, even partially or "just the first few
  characters."
- **Strip full local file paths that embed the OS username** (e.g.
  `C:\Users\<name>\...` or `/home/<name>/...`) — replace the username
  segment with something generic like `<user>` and keep the rest of the
  path if it's actually relevant to the issue.
- **Strip external URLs, hostnames, and IP addresses** that aren't
  necessary to explain the bug (a public HACS/GitHub URL that's already
  public is fine; the person's own HA instance URL, a local network
  hostname, or a home IP address is not).
- **Strip notify/device names that embed a real person's name** (e.g.
  `notify.mobile_app_johns_iphone` → describe it generically as "a mobile
  app notify target" instead).
- **Strip GPS coordinates** (a `zone.home` or weather entity's exact
  latitude/longitude) — describe the location only as generally as the
  issue actually needs (e.g. "tropical climate," not exact coordinates).

After redacting, **tell the person plainly what you removed and why**
before posting or handing over the draft — don't redact silently. If
you're unsure whether something is sensitive, treat it as sensitive and
ask, rather than including it and hoping it's fine.
