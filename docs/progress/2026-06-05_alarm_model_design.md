# BESS Alarm Model Design

## Goal

Create realistic BESS alarm behaviour for SCADA/operator testing without turning the simulator into random noise.

The alarm model should support:

- clear operator-facing alarm names and messages
- realistic warning, critical, and trip behaviour
- self-clearing process alarms where appropriate
- latched alarms for trip/interlock conditions
- clean separation between alarms and informational events
- future Ignition alarm displays, acknowledgement, and reset workflows
- optional fault injection for training and test scenarios

This document is a design proposal. It does not describe implemented code unless explicitly marked as implemented later.

## Existing Baseline

Current runtime already has:

- `bess_alarms` table for alarm/event records
- `site_status.active_alarms` as an integer active-alarm count
- OPC UA `Site/ActiveAlarms` exposing that count to Ignition
- basic site-level alarms for SOC, temperature, voltage, current, power limiting, and site power shortfall
- informational events such as startup and command received, stored as cleared records

Known baseline issues already addressed separately:

- `ApplyCommand` repeated command/event spam was fixed by forcing the OPC command node reset false after command processing.
- The local observer should treat `site_status.active_alarms` as a count and query `bess_alarms` separately for alarm names/details.

## Severity Model

| Severity | Numeric | Meaning | Operator expectation |
|---|---:|---|---|
| INFO | 1 | Event or diagnostic record, not an active alarm | Stored for history, not shown as active alarm |
| WARNING | 2 | Abnormal condition, plant can continue | Operator awareness, self-clears with hysteresis |
| CRITICAL | 3 | Serious process condition near limit | Operator action required, may inhibit affected command |
| TRIP | 4 | Protective trip/interlock/lockout | Latched, requires reset after condition clears |

Current code uses `FAULT = 4`. Proposed direction: rename operator-facing severity `FAULT` to `TRIP` or keep numeric 4 and display it as `TRIP/FAULT` until the schema/UI is updated.

## Alarm Record Model

The current `bess_alarms` table is enough for a first pass:

- `alarm_code`
- `severity`
- `message`
- `value`
- `threshold`
- `cleared`
- `cleared_ts`

Recommended future fields:

| Field | Purpose |
|---|---|
| `source_type` | Site, inverter, battery, comms, control |
| `source_id` | Optional equipment id, e.g. `INV03`, `BAT12` |
| `latched` | Whether alarm remains active until reset |
| `acknowledged` | Future Ignition acknowledgement workflow |
| `ack_ts` | Acknowledgement timestamp |
| `reset_required` | Whether reset is required after clear condition |
| `trigger_value` | Value at alarm raise, separate from current value |
| `clear_value` | Value at clear |

For the next implementation step, avoid schema changes unless needed. Source/id can be encoded in `alarm_code` and `message` initially.

## Behaviour Rules

### Self-clearing warnings

Warnings should clear automatically after the measured value returns to a normal range with hysteresis.

Example:

- trigger `SOC_HIGH` at `>= 90%`
- clear `SOC_HIGH` at `<= 88%`

This avoids alarm flicker around thresholds.

### Critical alarms

Critical alarms should also use hysteresis, but with a wider safe return margin.

Example:

- trigger `SOC_CRITICAL_HIGH` at `>= 95%`
- clear at `<= 93%`

Critical alarms may also inhibit unsafe commands, e.g. block charge at critical high SOC.

### Latched trip alarms

Trips should remain active after the trigger condition clears until a reset path is added.

Example:

- trigger `SITE_TRIP_ACTIVE` on critical temperature trip
- process value cools down
- trip remains active as `reset_required`
- operator reset clears it later

Initial implementation can log trip alarms as active and avoid auto-clear until manual reset support exists.

### Events are not alarms

Events should be inserted already cleared:

- `SYSTEM_START`
- `SYSTEM_STOP`
- `COMMAND_RECEIVED`
- `COMMAND_REJECTED`
- `COMMAND_ACCEPTED`
- `OPC_BRIDGE_START`

They should not affect active alarm count.

## Proposed Alarm Set - Stage 1

Stage 1 should focus on realistic site-level alarms that are easy to see in Ignition.

| Code | Severity | Source | Trigger | Clear condition | Latch | Operational effect |
|---|---|---|---|---|---|---|
| `SOC_HIGH` | WARNING | Site | SOC `>= 90%` | SOC `<= 88%` | No | Operator warning |
| `SOC_CRITICAL_HIGH` | CRITICAL | Site | SOC `>= 95%` | SOC `<= 93%` | No | Charge inhibit recommended |
| `SOC_LOW` | WARNING | Site | SOC `<= 10%` | SOC `>= 12%` | No | Operator warning |
| `SOC_CRITICAL_LOW` | CRITICAL | Site | SOC `<= 5%` | SOC `>= 7%` | No | Discharge inhibit recommended |
| `DC_BUS_HIGH` | WARNING | Site | Vdc `>= 850 V` | Vdc `<= 840 V` | No | Operator warning |
| `DC_BUS_LOW` | WARNING | Site | Vdc `<= 750 V` | Vdc `>= 760 V` | No | Operator warning |
| `TEMP_HIGH` | WARNING | Site | Temp `>= 35 C` | Temp `<= 33 C` | No | Operator warning |
| `TEMP_CRITICAL` | CRITICAL | Site | Temp `>= 45 C` | Temp `<= 42 C` | No initially | Power derate/trip later |
| `CURRENT_HIGH` | WARNING | Site | `abs(Idc) >= 300 A` | `abs(Idc) <= 280 A` | No | Operator warning |
| `CURRENT_CRITICAL` | CRITICAL | Site | `abs(Idc) >= 350 A` | `abs(Idc) <= 325 A` | No initially | Trip later |
| `SITE_POWER_SHORTFALL` | CRITICAL | Site | `abs(P_set - P_actual) > 5 kW` for 5 s while commanded | diff `<= 3 kW` or command idle | No | Indicates unable to meet command |

Notes:

- Rename current `VOLTAGE_HIGH/LOW` to `DC_BUS_HIGH/LOW` for operator clarity, or keep legacy codes and update messages only.
- Keep `SITE_POWER_SHORTFALL`; it has good SCADA training value.
- Drop active `POWER_LIMITED` as an alarm. If needed, log it as an INFO event or derive it from shortfall/derate later.

## Proposed Alarm Set - Stage 2

Stage 2 adds equipment-specific alarms based on inverter and battery telemetry.

| Code pattern | Severity | Source | Trigger | Clear condition | Latch | Operational effect |
|---|---|---|---|---|---|---|
| `INVxx_FAULT` | TRIP | Inverter | injected inverter fault true | manual reset | Yes | inverter unavailable |
| `INVxx_TEMP_HIGH` | WARNING | Inverter | inverter temp `>= 40 C` | `<= 37 C` | No | warning |
| `INVxx_TEMP_CRITICAL` | CRITICAL | Inverter | inverter temp `>= 50 C` | `<= 45 C` | Maybe | derate/trip later |
| `BATxx_FAULT` | TRIP | Battery | injected battery rack fault true | manual reset | Yes | battery unavailable |
| `BATxx_TEMP_HIGH` | WARNING | Battery | battery temp `>= 35 C` | `<= 33 C` | No | warning |
| `BATxx_TEMP_CRITICAL` | CRITICAL | Battery | battery temp `>= 45 C` | `<= 42 C` | Maybe | inhibit/derate later |
| `BATTERY_SOC_IMBALANCE` | WARNING | Battery fleet | max SOC - min SOC `>= 8%` | `<= 5%` | No | operator warning |
| `BATTERY_RACK_UNAVAILABLE` | WARNING | Battery | one rack faulted/unavailable | rack available | No/Maybe | reduced capacity later |

Stage 2 should avoid adding dozens of alarms to the UI at once. Start with fleet-level imbalance and one injected inverter/battery fault path.

## Proposed Alarm Set - Stage 3

Stage 3 adds communications and quality alarms.

| Code | Severity | Source | Trigger | Clear condition | Latch | Operational effect |
|---|---|---|---|---|---|---|
| `TELEMETRY_STALE` | CRITICAL | Data quality | latest `site_status.ts` age `> 10 s` from observer/bridge perspective | age `< 5 s` | No | SCADA data quality warning |
| `OPC_BRIDGE_STALE` | CRITICAL | OPC bridge | bridge cannot read DB or publish updates for `> 10 s` | successful reads resume | No | SCADA comms alarm |
| `DB_WRITE_FAILED` | CRITICAL | Simulator | simulator DB commit fails repeatedly | commit succeeds | No | telemetry unreliable |
| `BAD_SENSOR_VALUE` | WARNING | Data quality | impossible value, e.g. SOC outside 0-100, negative Vdc | value valid again | No | indicates simulation/data bug |

Implementation note: comms alarms may need bridge-side event logging, not only simulator-side logic.

## Fault Injection Design

Fault injection should be controlled and explicit. Avoid always-on randomness in the main loop until deterministic behaviour is stable.

Recommended controls:

- DB table `fault_injections`, or
- command table extension, or
- separate simple JSON/config file for lab testing

Starter scenarios:

| Scenario | Effect |
|---|---|
| `inject_inverter_fault(inv_id)` | Sets one inverter unavailable and raises `INVxx_FAULT` |
| `inject_battery_fault(bat_id)` | Sets one battery rack unavailable and raises `BATxx_FAULT` |
| `inject_dc_overvoltage(duration_s)` | Raises DC bus voltage above threshold temporarily |
| `inject_temp_rise(source, duration_s)` | Raises temp to warning/critical temporarily |
| `inject_comms_loss(duration_s)` | Stops bridge DB read/publish or marks telemetry stale |

Random testing can come later as scheduled scenario injection, for example one minor warning every 10-20 minutes during demo mode.

## Command Inhibit Rules

Command inhibit should be separate from alarm raise/clear logic so it is easy to reason about.

Recommended first-pass inhibit rules:

| Condition | Command affected | Behaviour |
|---|---|---|
| `SOC_CRITICAL_HIGH` active | CHARGE | reject or clamp to 0 kW |
| `SOC_CRITICAL_LOW` active | DISCHARGE | reject or clamp to 0 kW |
| `TEMP_CRITICAL` active | CHARGE/DISCHARGE | reject or derate |
| `SITE_TRIP_ACTIVE` active | CHARGE/DISCHARGE | reject until reset |

Rejected commands should log an INFO event `COMMAND_REJECTED`, not an active alarm by itself.

## Implementation Sequence Proposal

1. Add hysteresis support to alarm checks.
2. Normalize site alarm codes/messages.
3. Remove or demote `POWER_LIMITED` from active alarm behaviour.
4. Add command inhibit for critical high/low SOC.
5. Add one latched trip path, probably `SITE_TRIP_ACTIVE`, only after reset behaviour is designed.
6. Add equipment/fault injection alarms in a later stage.
7. Add Ignition alarm table/display improvements after DB alarm behaviour is stable.

## Acceptance Criteria

The alarm work is successful when:

- `site_status.active_alarms` matches active non-INFO rows in `bess_alarms`.
- SOC warning/critical alarms raise and clear with hysteresis.
- Informational events do not increase active alarm count.
- A realistic alarm list is visible to Ignition/operator displays.
- Repeated command writes do not create alarm/event spam.
- At least one alarm scenario can be demonstrated and cleared cleanly.
- Later, at least one latched trip can be demonstrated with manual reset.
