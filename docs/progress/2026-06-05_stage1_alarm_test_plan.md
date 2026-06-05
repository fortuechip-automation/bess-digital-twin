# Stage 1 Alarm Test Plan

## Purpose

Validate the Stage 1 BESS alarm changes before doing further alarm work.

This test plan is deliberately split into non-runtime checks and optional live checks so the simulator, OPC bridge, tmux sessions, and database are not touched without explicit approval.

## Scope

Stage 1 alarm behaviour under review:

- site alarm hysteresis
- SOC high/low/critical alarm behaviour
- temperature warning/critical alarm behaviour
- DC bus high/low alarm naming and hysteresis
- current high/critical alarm naming and hysteresis
- `SITE_POWER_SHORTFALL` debounce and clear threshold
- legacy/noisy alarm cleanup
- active alarm count consistency

## Review Decisions

Decisions captured before test execution:

- Warning and critical alarms are allowed to coexist.
- Current hysteresis values are acceptable for this pass.
- `SITE_POWER_SHORTFALL` should be treated as `FAULT/TRIP`.
- No live runtime tests should run without explicit approval of the exact action.

Out of scope for this test pass:

- equipment-specific alarms
- random fault injection
- latched trip/reset workflow
- Ignition alarm table UI changes
- schema changes
- command inhibit logic

## Safety Rules

No one should run live tests from this plan until the exact step is explicitly approved.

Explicit approval is required before:

- stopping the simulator
- restarting the simulator
- stopping or restarting the OPC bridge
- sending test commands from Ignition
- inserting/updating/deleting DB rows
- clearing live alarm rows
- changing tmux processes
- committing or pushing additional changes

Safe without live-runtime approval:

- reading source files
- reviewing this plan
- running static checks such as `py_compile`
- creating a separate offline/unit-style test file that does not connect to the live DB

## Test Method Options

### Option A - Offline function-level test, recommended first

Goal: test alarm decision logic without touching the live simulator or database.

Approach:

- Build a small test harness or unit test that imports/exercises alarm helper logic with fake cursor/state.
- Use fake alarm state and fake DB cursor calls.
- Verify which alarms would raise/clear for controlled values.
- No live DB connection.
- No tmux changes.
- No simulator restart.

Pros:

- safest first check
- repeatable
- can catch threshold/hysteresis mistakes

Cons:

- does not prove full runtime DB insert/clear behaviour

### Option B - Controlled live runtime test, later only by explicit approval

Goal: prove behaviour through the live simulator/database path.

Approach:

- Use tmux so the simulator and bridge output remain visible during the test.
- Use controlled simulator state or commands.
- Observe `bess_alarms`, `site_status.active_alarms`, and Ignition values.

Pros:

- proves end-to-end behaviour

Cons:

- touches live runtime
- may require simulator restart or controlled test hooks
- can affect dashboard state/history

Recommendation: do Option A first. Only move to Option B after the offline results are reviewed.

## Expected Alarm Rules

| Alarm | Trigger | Clear | Expected severity |
|---|---:|---:|---|
| `SOC_HIGH` | SOC `>= 90%` | SOC `<= 88%` | WARNING |
| `SOC_CRITICAL_HIGH` | SOC `>= 95%` | SOC `<= 93%` | CRITICAL |
| `SOC_LOW` | SOC `<= 10%` | SOC `>= 12%` | WARNING |
| `SOC_CRITICAL_LOW` | SOC `<= 5%` | SOC `>= 7%` | CRITICAL |
| `TEMP_HIGH` | Temp `>= 35 C` | Temp `<= 33 C` | WARNING |
| `TEMP_CRITICAL` | Temp `>= 45 C` | Temp `<= 42 C` | CRITICAL |
| `DC_BUS_HIGH` | Vdc `>= 850 V` | Vdc `<= 840 V` | WARNING |
| `DC_BUS_LOW` | Vdc `<= 750 V` | Vdc `>= 760 V` | WARNING |
| `CURRENT_HIGH` | `abs(Idc) >= 300 A` | `abs(Idc) <= 280 A` | WARNING |
| `CURRENT_CRITICAL` | `abs(Idc) >= 350 A` | `abs(Idc) <= 325 A` | CRITICAL |
| `SITE_POWER_SHORTFALL` | diff `> 5 kW` for 5 seconds | diff `<= 3 kW` or idle command | FAULT/TRIP |

## Offline Test Cases

### TC-A1 - Normal state produces no alarms

Input:

- SOC `50%`
- Temp `25 C`
- Vdc `800 V`
- Idc `0 A`
- P_set `0 kW`
- P_actual `0 kW`

Expected:

- no active non-INFO alarms
- no legacy alarms active
- active alarm count would be `0`

### TC-A2 - SOC high raises and holds until clear threshold

Sequence:

1. SOC `89.9%`
2. SOC `90.0%`
3. SOC `89.0%`
4. SOC `88.1%`
5. SOC `88.0%`

Expected:

- no alarm at `89.9%`
- `SOC_HIGH` raises at `90.0%`
- `SOC_HIGH` remains active at `89.0%` and `88.1%`
- `SOC_HIGH` clears at `88.0%`

### TC-A3 - SOC high and critical high can coexist

Sequence:

1. SOC `94.0%`
2. SOC `95.0%`
3. SOC `94.0%`
4. SOC `93.0%`

Expected:

- `SOC_HIGH` may be active below critical threshold if already triggered
- `SOC_CRITICAL_HIGH` raises at `95.0%`
- `SOC_HIGH` may remain active at the same time as `SOC_CRITICAL_HIGH`
- `SOC_CRITICAL_HIGH` remains active at `94.0%`
- `SOC_CRITICAL_HIGH` clears at `93.0%`

Review decision:

- Warning and critical alarms are allowed to coexist.

### TC-A4 - SOC low and critical low hysteresis

Sequence:

1. SOC `10.0%`
2. SOC `8.0%`
3. SOC `5.0%`
4. SOC `6.0%`
5. SOC `7.0%`
6. SOC `12.0%`

Expected:

- `SOC_LOW` raises at `10.0%`
- `SOC_CRITICAL_LOW` raises at `5.0%`
- `SOC_LOW` may remain active at the same time as `SOC_CRITICAL_LOW`
- `SOC_CRITICAL_LOW` remains active at `6.0%`
- `SOC_CRITICAL_LOW` clears at `7.0%`
- `SOC_LOW` clears at `12.0%` if it becomes active again after critical clears

### TC-A5 - Temperature high/critical hysteresis

Sequence:

1. Temp `34.9 C`
2. Temp `35.0 C`
3. Temp `44.0 C`
4. Temp `45.0 C`
5. Temp `43.0 C`
6. Temp `42.0 C`
7. Temp `33.0 C`

Expected:

- no alarm at `34.9 C`
- `TEMP_HIGH` raises at `35.0 C`
- `TEMP_CRITICAL` raises at `45.0 C`
- `TEMP_HIGH` may remain active with `TEMP_CRITICAL`
- `TEMP_CRITICAL` remains active at `43.0 C`
- `TEMP_CRITICAL` clears at `42.0 C`
- `TEMP_HIGH` clears at `33.0 C` if active

### TC-A6 - DC bus high/low hysteresis

High sequence:

1. Vdc `849.9 V`
2. Vdc `850.0 V`
3. Vdc `845.0 V`
4. Vdc `840.0 V`

Expected:

- `DC_BUS_HIGH` raises at `850.0 V`
- remains active at `845.0 V`
- clears at `840.0 V`

Low sequence:

1. Vdc `750.1 V`
2. Vdc `750.0 V`
3. Vdc `755.0 V`
4. Vdc `760.0 V`

Expected:

- `DC_BUS_LOW` raises at `750.0 V`
- remains active at `755.0 V`
- clears at `760.0 V`

### TC-A7 - Current high/critical hysteresis

Sequence:

1. Idc `299.9 A`
2. Idc `300.0 A`
3. Idc `349.0 A`
4. Idc `350.0 A`
5. Idc `330.0 A`
6. Idc `325.0 A`
7. Idc `280.0 A`

Expected:

- `CURRENT_HIGH` raises at `300.0 A`
- `CURRENT_CRITICAL` raises at `350.0 A`
- `CURRENT_HIGH` may remain active with `CURRENT_CRITICAL`
- `CURRENT_CRITICAL` remains active at `330.0 A`
- `CURRENT_CRITICAL` clears at `325.0 A`
- `CURRENT_HIGH` clears at `280.0 A` if active

Repeat with negative current values to verify `abs(Idc)` behaviour.

### TC-A8 - Site power shortfall debounce and clear

Sequence:

- P_set `20 kW`, P_actual `14 kW`, diff `6 kW`, repeated for 4 checks
- same diff for 5th check
- then P_actual `17.5 kW`, diff `2.5 kW`

Expected:

- no alarm for first 4 checks
- `SITE_POWER_SHORTFALL` raises on 5th consecutive check
- remains active while diff is above clear threshold
- clears when diff `<= 3 kW`

### TC-A9 - Idle command clears site power shortfall

Input:

- existing active `SITE_POWER_SHORTFALL`
- P_set `0 kW`
- P_actual `0 kW`

Expected:

- shortfall counter resets
- `SITE_POWER_SHORTFALL` clears

### TC-A10 - Legacy/noisy alarms are not active

Legacy codes to check:

- `POWER_LIMITED`
- `CHARGE_AT_HIGH_SOC`
- `DISCHARGE_AT_LOW_SOC`
- `VOLTAGE_HIGH`
- `VOLTAGE_LOW`
- `TEMP_WARNING`
- `CURRENT_WARNING`

Expected:

- these should not remain active after Stage 1 alarm checks run
- if present from old runs, they should be cleared

## Optional Live Test Cases

These require separate explicit approval.

### TC-B1 - Live normal state check

Read-only checks only:

- latest `site_status`
- active rows in `bess_alarms`
- local observer status output

Expected:

- fresh data
- `site_status.active_alarms` equals active non-INFO alarm row count
- no repeated `COMMAND_RECEIVED` event spam

### TC-B2 - Live SOC high test

Requires explicit approval and a safe way to drive SOC above threshold.

Possible approaches:

- long charge run
- temporary controlled simulator initial state/test hook
- DB-only synthetic test is not preferred unless clearly isolated from live runtime

Expected:

- `SOC_HIGH` raises at high SOC
- clears only after SOC drops to clear threshold

### TC-B3 - Live site shortfall test

Requires explicit approval.

Possible approaches:

- command above plant capability if model supports saturation
- temporary controlled derate/fault injection later

Expected:

- `SITE_POWER_SHORTFALL` raises after debounce
- clears when mismatch returns below clear threshold or idle command is applied

## Review Questions Before Any Test Execution

1. Warning and critical alarms are **not** mutually exclusive; both may remain active.
2. Hysteresis values are accepted for this test pass.
3. Stage 1 command inhibit remains deferred unless separately approved.
4. `SITE_POWER_SHORTFALL` should be `FAULT/TRIP`, not `CRITICAL`.
5. Legacy alarm cleanup remains to be reviewed during tests.

## Proposed Next Action

After this plan is reviewed, the safest next action is:

1. create an offline test harness for TC-A1 through TC-A10
2. run the offline tests only
3. report pass/fail and any suggested code adjustments
4. only then decide whether to run live tests
