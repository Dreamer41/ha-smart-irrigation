# Releasing ZoneFlow

Checklist for every release (GitHub release titled "ZoneFlow X.Y.Z", tag
`vX.Y.Z`).

1. `custom_components/zoneflow/manifest.json` version bumped.
2. Full test suite passes (`pytest tests/ -q`) and the GitHub checks
   (Tests, HASSfest, HACS) are green.
3. README.md and AI_SETUP.md describe the new behaviour (AI_SETUP's
   dashboard template in §9 includes any new entities).
4. ROADMAP.md: move shipped items to "Shipped".
5. **Release notes always include an "Update your dashboard" section.**
   Existing users' dashboards don't change on their own, so whenever a
   release adds, renames or removes an entity people would want on their
   dashboard, the notes must say:
   - which entities are new (with their entity ID pattern, e.g.
     `switch.<zone>_service_mode`),
   - which card they belong on,
   - step-by-step how to add them in the Home Assistant UI (Edit
     dashboard → the card → Show code editor), with a ready-to-paste YAML
     snippet using `<zone>` as the placeholder for the zone's entity
     prefix,
   - and the shortcut: paste AI_SETUP.md into an AI assistant and ask it
     to update the dashboard for this version.
   If a release adds nothing for the dashboard, the section says so in one
   line ("No dashboard changes needed").
6. Release notes also say whether anything needs doing after the update
   (usually "nothing — just restart Home Assistant").
