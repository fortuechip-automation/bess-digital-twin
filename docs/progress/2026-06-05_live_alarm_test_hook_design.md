# Live Alarm Test Hook Design

## Purpose

Add a controlled way to trigger and clear BESS alarms during live SCADA testing without waiting for natural simulator drift and without manually editing live telemetry rows.

The hook should support repeatable live alarm tests through the normal simulator -> PostgreSQL -> OPC UA -> Ignition path.

## Design Goals

- Explicit operator/test action only; no random faults by default.
- Expiring test scenarios so faults do not stay active accidentally.
- Clear separation between normal simulation state and test overrides.
- Minimal first implementation.
- No Ignition UI requirement for the first pass; DB insert commands are acceptable for engineering tests.
- No schema changes to existing telemetry or alarm tables unless necessary.
- Easy to disable or ignore when not testing.

## Non-Goals

- Full fault-injection framework.
- Random alarm generation.
- Latched trip/reset workflow.
- Equipment-specific inverter/battery fault injection.
- Ignition alarm management UI.
- Permanent EMS/control inhibit logic.

## Recommended Approach

Create a small PostgreSQL table called `alarm_test_injections`.

The simulator reads active rows from this table once per loop. If a row is active and not expired, the simulator applies a temporary override to the values used by alarm checks.

The simulator should still write normal-looking telemetry to `site_status`, but with test values applied for the active scenario. This allows the OPC bridge and Ignition to see the alarm condition through the normal live path.

## Proposed Table

```sql
CREATE TABLE IF NOT EXISTS alarm_test_injections (
    injection_id SERIAL PRIMARY KEY,
    created_ts TIMESTAMPTZ DEFAULT NOW(),
    enabled BOOLEAN DEFAULT TRUE,
    scenario TEXT NOT NULL,
    target TEXT DEFAULT 'site',
    value REAL,
    duration_seconds INTEGER DEFAULT 60,
    expires_ts TIMESTAMPTZ,
    note TEXT,
    consumed BOOLEAN DEFAULT FALSE
);
```

Recommended behaviour:

- If `expires_ts` is null, simulator calculates expiry as `created_ts + duration_seconds`.
- Active injections are rows where:
  - `enabled = TRUE`
  - `consumed = FALSE`
  - current time is before expiry
- When expired, simulator marks the row `consumed = TRUE` or simply ignores it.
- Only one active injection should be applied at a time in Stage 1 to avoid confusing results.

## Stage 1 Scenarios

| Scenario | Value meaning | Alarm target | Expected alarm |
|---|---:|---|---|
| `FORCE_SOC` | SOC percent | Site SOC | `SOC_HIGH`, `SOC_CRITICAL_HIGH`, `SOC_LOW`, `SOC_CRITICAL_LOW` |
| `FORCE_TEMP` | Site temp C | Site temp | `TEMP_HIGH`, `TEMP_CRITICAL` |
| `FORCE_VDC` | DC bus voltage | Site Vdc | `DC_BUS_HIGH`, `DC_BUS_LOW` |
| `FORCE_IDC` | DC current A | Site Idc | `CURRENT_HIGH`, `CURRENT_CRITICAL` |
| `FORCE_POWER_SHORTFALL` | actual power override kW | Site power mismatch | `SITE_POWER_SHORTFALL` |

## Scenario Details

### `FORCE_SOC`

Override the site SOC value used for alarm checks and `site_status` insert.

Examples:

```sql
INSERT INTO alarm_test_injections (scenario, value, duration_seconds, note)
VALUES ('FORCE_SOC', 96.0, 30, 'Test SOC critical high alarm');
```

Expected:

- SOC appears near `96%` in live telemetry.
- `SOC_HIGH` and `SOC_CRITICAL_HIGH` become active.
- When injection expires, SOC returns to simulator-calculated value.
- Critical/high alarms clear only after values cross hysteresis clear thresholds.

Review note:

- Because hysteresis clear thresholds are below the trigger thresholds, returning to normal SOC around 50% should clear both alarms cleanly.

### `FORCE_TEMP`

Override site temperature.

Example:

```sql
INSERT INTO alarm_test_injections (scenario, value, duration_seconds, note)
VALUES ('FORCE_TEMP', 46.0, 30, 'Test site temperature critical alarm');
```

Expected:

- `TEMP_HIGH` and `TEMP_CRITICAL` become active.
- Both clear when injection expires and temperature returns below clear thresholds.

### `FORCE_VDC`

Override site DC bus voltage.

High example:

```sql
INSERT INTO alarm_test_injections (scenario, value, duration_seconds, note)
VALUES ('FORCE_VDC', 855.0, 30, 'Test DC bus high alarm');
```

Low example:

```sql
INSERT INTO alarm_test_injections (scenario, value, duration_seconds, note)
VALUES ('FORCE_VDC', 745.0, 30, 'Test DC bus low alarm');
```

Expected:

- High value raises `DC_BUS_HIGH`.
- Low value raises `DC_BUS_LOW`.
- Alarm clears after expiry once normal Vdc returns past clear threshold.

### `FORCE_IDC`

Override site DC current.

Example:

```sql
INSERT INTO alarm_test_injections (scenario, value, duration_seconds, note)
VALUES ('FORCE_IDC', 360.0, 30, 'Test current critical alarm');
```

Expected:

- `CURRENT_HIGH` and `CURRENT_CRITICAL` become active.
- Negative values should behave the same because alarm logic uses absolute current.

### `FORCE_POWER_SHORTFALL`

Override `p_actual_kw` while keeping current `p_set_kw` from command state.

Example when the simulator is commanded to `20 kW`:

```sql
INSERT INTO alarm_test_injections (scenario, value, duration_seconds, note)
VALUES ('FORCE_POWER_SHORTFALL', 10.0, 15, 'Test site power shortfall alarm');
```

Expected:

- If mismatch remains above `5 kW` for 5 loop cycles, `SITE_POWER_SHORTFALL` raises as `FAULT`.
- It clears after actual power returns close enough to setpoint or after idle command.

Review note:

- This scenario requires a non-zero command setpoint. It should not be run while the site is idle unless the test deliberately sets both command and actual values.

## Safety Behaviour

The simulator should print a clear line when an injection is active:

```text
[TEST] Applying alarm injection FORCE_SOC value=96.0 expires=...
```

The simulator should also log an INFO event when an injection starts:

- `ALARM_TEST_INJECTION_STARTED`

And when it expires:

- `ALARM_TEST_INJECTION_ENDED`

These should be cleared INFO events and should not increase active alarm count.

## Implementation Sketch

### Read active injection

Add helper:

```python
def read_active_alarm_test_injection(cur):
    ...
```

It returns either `None` or a dict:

```python
{
    "injection_id": 1,
    "scenario": "FORCE_SOC",
    "value": 96.0,
    "expires_ts": ...,
}
```

### Apply injection

After `simulate_fleet_step(p_set_kw)` returns `site_tuple`, apply the override before alarm checks and DB insert:

```python
soc_site, mode_site, p_set_site, p_actual_site, vdc_site, idc_site, temp_site = site_tuple

injection = read_active_alarm_test_injection(cur)
if injection:
    soc_site, mode_site, p_set_site, p_actual_site, vdc_site, idc_site, temp_site = apply_alarm_test_injection(
        injection,
        soc_site,
        mode_site,
        p_set_site,
        p_actual_site,
        vdc_site,
        idc_site,
        temp_site,
    )
```

Then run:

```python
check_all_alarms(...)
update_site_shortfall_alarm(...)
insert_site(...)
```

This makes the injected condition visible through DB, OPC UA, and Ignition.

## Expiry and Cleanup

On each loop, the simulator can mark expired rows consumed:

```sql
UPDATE alarm_test_injections
SET consumed = TRUE, enabled = FALSE
WHERE enabled = TRUE
  AND consumed = FALSE
  AND COALESCE(expires_ts, created_ts + duration_seconds * INTERVAL '1 second') <= NOW();
```

This keeps the table tidy and prevents old injections from reappearing after simulator restart.

## Stage 1 Live Test Sequence

After implementation and explicit approval, the live tests should run in this order:

1. Confirm normal live state is healthy.
2. Inject `FORCE_SOC = 96` for 30 seconds.
3. Verify `SOC_HIGH` and `SOC_CRITICAL_HIGH` active.
4. Wait for expiry.
5. Verify both clear.
6. Inject `FORCE_TEMP = 46` for 30 seconds.
7. Verify `TEMP_HIGH` and `TEMP_CRITICAL` active.
8. Wait for expiry and verify clear.
9. Inject `FORCE_VDC = 855` and verify `DC_BUS_HIGH`.
10. Inject `FORCE_IDC = 360` and verify `CURRENT_HIGH` and `CURRENT_CRITICAL`.
11. Run power shortfall test only if a non-zero setpoint is active and approved.

## Acceptance Criteria

The live alarm hook is acceptable when:

- injections are explicit and time-limited
- no random faults occur during normal operation
- injected values appear in `site_status`
- OPC bridge reports the injected values to Ignition
- expected alarms raise through `bess_alarms`
- alarm count in `site_status` matches active non-INFO alarm rows
- alarms clear after injection expiry and hysteresis clear condition
- INFO test events do not increase active alarm count
- no repeated command/event spam appears during tests

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Injection left active too long | expiry/consumed fields |
| Confusing live dashboard values | `[TEST]` console output and INFO events |
| Multiple conflicting injections | Stage 1 applies only the newest/first active injection |
| Hidden DB writes during review | do not create table or insert rows until implementation is approved |
| Accidentally committing test-only behaviour as always-on random faults | keep feature explicit and disabled unless table rows exist |

## Recommendation

Implement this hook after review, starting with only these scenarios:

- `FORCE_SOC`
- `FORCE_TEMP`
- `FORCE_VDC`
- `FORCE_IDC`

Defer `FORCE_POWER_SHORTFALL` until the simpler value-driven alarms are proven live.
