# Stage 2 Equipment Alarm Implementation

## Summary

Stage 2 extends the BESS alarm model from site-level alarms into equipment-level
inverter, battery, and fleet alarms.

The implementation deliberately avoids a database migration. Equipment source is
encoded in the existing `alarm_code` field so the current PostgreSQL, OPC UA, and
Ignition paths can continue to work while providing more specific alarm names.

## Implemented alarms

| Alarm code pattern | Severity | Trigger | Clear condition |
|---|---|---|---|
| `INVxx_TEMP_HIGH` | WARNING | inverter temp `>= 40 C` | inverter temp `<= 37 C` |
| `INVxx_TEMP_CRITICAL` | CRITICAL | inverter temp `>= 50 C` | inverter temp `<= 45 C` |
| `INVxx_UNAVAILABLE` | WARNING | inverter fault flag true | inverter fault flag false |
| `BATxx_TEMP_HIGH` | WARNING | battery temp `>= 35 C` | battery temp `<= 33 C` |
| `BATxx_TEMP_CRITICAL` | CRITICAL | battery temp `>= 45 C` | battery temp `<= 42 C` |
| `BATxx_UNAVAILABLE` | WARNING | battery fault flag true | battery fault flag false |
| `BATTERY_SOC_IMBALANCE` | WARNING | max/min battery SOC spread `>= 8%` | spread `<= 5%` |

Examples:

- `INV03_TEMP_HIGH`
- `BAT12_TEMP_CRITICAL`
- `BATTERY_SOC_IMBALANCE`

## Runtime integration

The simulator now checks equipment alarms after each fleet step and after the
existing site-level alarm checks. The active alarm count stored in `site_status`
therefore includes Stage 1 site alarms and Stage 2 equipment alarms.

## Controlled live injection

The existing PostgreSQL `alarm_test_injections` table now supports controlled
equipment-level scenarios. The simulator applies the newest enabled, unexpired
injection to telemetry rows before alarm checks and inserts, so Ignition can see
both the forced telemetry value and the resulting alarm.

Supported Stage 2 scenarios:

| Scenario | Target examples | Value | Effect |
|---|---|---:|---|
| `FORCE_INV_TEMP` | `INV03`, `3` | temp C | Overrides one inverter temperature |
| `FORCE_INV_FAULT` | `INV03`, `3` | `1` or blank | Forces one inverter fault/unavailable flag |
| `FORCE_BAT_TEMP` | `BAT12`, `12` | temp C | Overrides one battery temperature |
| `FORCE_BAT_FAULT` | `BAT12`, `12` | `1` or blank | Forces one battery fault/unavailable flag |
| `FORCE_BAT_SOC` | `BAT12`, `12` | SOC % | Overrides one battery SOC for imbalance testing |

Example injections:

```sql
INSERT INTO alarm_test_injections (scenario, target, value, duration_seconds, note)
VALUES ('FORCE_INV_TEMP', 'INV03', 50.0, 60, 'Test INV03 critical temp alarm');

INSERT INTO alarm_test_injections (scenario, target, value, duration_seconds, note)
VALUES ('FORCE_BAT_TEMP', 'BAT12', 45.0, 60, 'Test BAT12 critical temp alarm');

INSERT INTO alarm_test_injections (scenario, target, value, duration_seconds, note)
VALUES ('FORCE_INV_FAULT', 'INV04', 1.0, 60, 'Test INV04 unavailable alarm');

INSERT INTO alarm_test_injections (scenario, target, value, duration_seconds, note)
VALUES ('FORCE_BAT_SOC', 'BAT02', 70.0, 60, 'Test battery SOC imbalance alarm');
```

Injections expire automatically using the existing `duration_seconds`/`expires_ts`
logic. When they expire, the simulator returns to normal generated telemetry and
the Stage 2 alarms clear through their normal clear conditions.

## Boundaries

This stage does not add:

- latched trip/manual-reset behaviour
- command inhibit logic
- alarm acknowledgement fields
- database source-type/source-id columns
- random equipment fault injection

Those are still better handled as a later alarm lifecycle and operator workflow
step.

## Validation

Automated tests cover:

- inverter warning/critical temperature hysteresis
- battery warning/critical temperature hysteresis
- inverter and battery unavailable raise/clear behaviour
- battery SOC imbalance hysteresis
- zero-padded equipment alarm code formatting
- combined Stage 2 checker dispatch
- controlled inverter temp/fault injection
- controlled battery temp/fault/SOC injection

Live smoke validation after simulator restart confirmed:

- simulator restarted cleanly with the Stage 2 code
- OPC bridge remained running
- telemetry returned to fresh status
- latest equipment telemetry included 10 inverter rows and 20 battery rows
- inverter and battery fault counts were zero
- equipment temperatures and battery SOC spread were below Stage 2 thresholds
- active alarm count remained zero

Forced live equipment alarm scenarios were validated after a runtime restart.

Validated live injections:

| Scenario | Target | Expected alarm result |
|---|---|---|
| `FORCE_INV_TEMP` | `INV03` | `INV03_TEMP_HIGH`, `INV03_TEMP_CRITICAL` raised and cleared |
| `FORCE_BAT_TEMP` | `BAT12` | `BAT12_TEMP_HIGH`, `BAT12_TEMP_CRITICAL` raised and cleared |
| `FORCE_INV_FAULT` | `INV04` | `INV04_UNAVAILABLE` raised and cleared |
| `FORCE_BAT_FAULT` | `BAT07` | `BAT07_UNAVAILABLE` raised and cleared |
| `FORCE_BAT_SOC` | `BAT02` | `BATTERY_SOC_IMBALANCE` raised and cleared |

Final active alarm state after validation: no active alarms.
