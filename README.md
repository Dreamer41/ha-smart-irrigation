# HA Smart Irrigation

Home Assistant custom integration for smart avocado irrigation.

## Current status

**Integration candidate — ready for live testing.**

The implementation is based on the existing, carefully tuned Home Assistant YAML reference. The YAML architecture was translated rather than redesigned:

- Routine target remains a weekly target scaled to the actual 3- or 4-day interval.
- Effective rainfall remains the matching 4-day rainfall multiplied by configurable efficiency.
- Significant rain remains 35 mm / 24h, 50 mm / 4d, or 100 mm / 7d.
- A rain tip continuously refreshes the significant-rain timestamp while a threshold remains met, giving the tail end of the storm as the dry-down reference.
- Routine irrigation uses the 3-day average peak temperature source and the 31.5 C hot threshold.
- Deep soak remains a 14-day schedule check, 8-day post-significant-rain dry-down, 40 mm 14-day rain ceiling, 25 mm target, three pulses and 20-minute rests.
- Pump power remains an audit warning rather than an irrigation abort because the household pump is shared.
- The routine runtime preserves the reference YAML's existing `runtime - 1 minute` execution behavior.
- Valve watchdog remains a 150-minute hard cutoff.
- Mutex watchdog remains a 180-minute hard cutoff.
- Fault lockout remains manual-reset only after a watchdog fault.

### Rain architecture

The integration uses a persistent tip-driven lifetime accumulator and derives 24h / 4d / 7d / 14d windows from tip timestamps. It does not sum rolling snapshots, avoiding the double-counting problem in the old array design.

### Configuration

Setup uses Home Assistant searchable entity selectors. The tuning values are native HA `number` entities and persist in the config entry, so tuning does not require editing YAML.

### Main entities

Rainfall:

- Rain Lifetime
- Rain Past 24h
- Rain Past 4d
- Rain Past 7d
- Rain Past 14d

Diagnostics:

- Interval Target
- Effective Rain
- Irrigation Deficit
- Calculated Routine Runtime
- Deep Soak Runtime
- Deep Soak Pulse Runtime

Controls/safety:

- Irrigation Active
- Fault Lockout
- Run Routine Now
- Run Deep Soak Now
- Clear Fault Lockout

## Installation for live testing

1. In Home Assistant, install this custom component under `custom_components/avocado_irrigation/` from this repository/branch.
2. Restart Home Assistant.
3. Add **Avocado Irrigation** through **Settings → Devices & services → Add Integration**.
4. Select your existing irrigation valve, rain-gauge tip sensor, pump-power sensor, and **3-day average peak temperature sensor**.
5. Leave the defaults at the values from the reference system unless you intentionally want to tune them.
6. Verify the diagnostic sensors before allowing the first scheduled run.

### Important

The integration now contains automatic valve control. Remove/disable the old avocado irrigation automations before the first scheduled run so the two systems cannot operate the same valve independently.

The manual **Run Routine Now** and **Run Deep Soak Now** buttons bypass the normal schedule/interval checks, but they do **not** bypass the hard fault lockout or active mutex.

## Development

The implementation is being developed on `feature/integration-foundation` before promotion to `main`. GitHub Actions contains regression tests for the reference calculations.
