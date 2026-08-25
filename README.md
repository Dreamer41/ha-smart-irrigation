# HA Smart Irrigation

Home Assistant custom integration for smart avocado irrigation.

## Project status

**Phase 0.1 — foundation / calculation engine**

The current repository starts from the working Home Assistant YAML implementation. The first goal is to reproduce and test its irrigation mathematics before replacing any live valve automation.

### Reference logic preserved

- Weekly routine target is scaled to the actual 3- or 4-day interval.
- Effective rainfall uses the matching 4-day rainfall window and configurable rain efficiency.
- Routine runtime is derived from irrigation deficit and calibrated flow rate.
- Deep soak uses a three-pulse calculation with the existing runtime safety cap.
- Significant rain uses the 24h / 4d / 7d thresholds from the reference system.
- Safety and valve control will be added only after the calculation results have been validated against the existing HA automation.

## Migration strategy

The existing Home Assistant automation should remain active while this integration is developed and tested. The integration will initially expose calculations and diagnostics without taking control of the irrigation valve.

Planned stages:

1. Calculation engine and tests
2. HA sensors and configurable parameters
3. Rain-gauge integration and rolling rainfall tracking
4. Irrigation mutex and fault lockout
5. Valve and pump control
6. Deep-soak and routine scheduling
7. Dashboard/configuration polish and HACS packaging

## Development branch

The initial implementation is being developed on `feature/integration-foundation`. It should be compared with the live YAML before merging into `main`.
