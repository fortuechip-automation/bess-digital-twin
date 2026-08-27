# Watchdog Alarm — Root Cause and Fix (2026-08-17)

Follow-up to `2026-08-13_panel_and_heartbeat_gap.md` and the step-4 build, which
left the watchdog half-working: the memory tag `[default]BESS1/ControlMode`
flipped to `EMS OFFLINE` correctly and its bell reacted, but the alarm never
registered as an event — `system.alarm.queryStatus()` returned only Ignition's
8 bundled demo alarms. This session finds the cause and fixes it.

## Prior hypothesis, falsified

The standing theory was that Trial Mode gateway restarts were wiping
memory-only alarm history (no Alarm Journal is configured), so events fired but
did not survive to be queried.

Falsified directly: holding `ControlMode` at `EMS OFFLINE` for 10 seconds —
rewriting it 4x/second to beat the `PollControlMode` timer script, which
otherwise restores the query result within ~1 second — and querying while held
still returned 8 alarms. Nothing was being wiped. The alarm never fired.

## Root cause

`setpointA` is a **numeric** property in Ignition's alarm model. An alarm whose
setpoint is compared against a **String** tag value cannot evaluate, and fails
silently — no exception, no gateway log entry, and `getConfiguration()` still
reports the stored setpoint as if it were valid.

Confirmed by dumping a known-working alarm alongside ours. The demo alarms live
in the `Sample_Tags` provider (visible in each event's `source`, e.g.
`prov:Sample_Tags:/tag:Ramp/Ramp3:/alm:High Alarm`), not `default`:

| Tag                        | dataType | setpointA                | mode           |
|----------------------------|----------|--------------------------|----------------|
| `Ramp3`                    | Float8   | `9.0`                    | Above Setpoint |
| `WriteableBoolean1`        | Boolean  | `1.0`                    | (default)      |
| `WriteableInteger1`        | Int4     | `90.0` / `10.0`          | Above / Below  |
| `BESS1/ControlMode` (ours) | String   | Expression `"EMS OFFLINE"` | (default)    |

Every working setpoint on this gateway is numeric, including the Boolean one.

This also explains the "Designer widget bug" recorded on 2026-08-13: the plain
Setpoint field refused typed text because it is a numeric field. Binding it to
an Expression stored the string but never made it evaluable.

## Fix

Alarm on a Boolean derived from the String, mirroring the working
`WriteableBoolean1` pattern. New expression tag:

    [default]BESS1/EMSOfflineFlag   (Boolean, valueSource: expr)
    {[default]BESS1/ControlMode} = "EMS OFFLINE"

with the alarm attached to it:

    name        EMSOffline
    displayPath EMS Offline
    priority    High
    setpointA   1.0

The defunct alarm was removed from `ControlMode`. No changes to the
`PollControlMode` timer script, the Named Queries (`sql/control_mode.sql`,
`sql/override_seconds_left.sql`) or the Perspective panel — the control-mode
lamp and countdown are untouched.

## Verification (live)

Forced test: alarm count 8 → 13, with `EMS Offline` events registering.

End-to-end test, the real failure path: `bess-ems` stopped on bems, heartbeat
allowed to age past the 12-minute staleness threshold. The chain ran unattended
— timer script wrote `ControlMode = EMS OFFLINE`, the expression tag derived
`true`, and the alarm raised:

    EMS Offline | state=Active, Unacknowledged | acked=False | active=True

The project's Alarm Status Table now lists it (`prov:default:/tag:BESS1/
EMSOfflineFlag`). That table showed only demo alarms on 2026-08-13 — it was
never filtering ours out; the alarm did not exist in an evaluable form.

Note: the Tag Browser bell icon in Designer stayed gray throughout while both
`queryStatus()` and the Alarm Status Table reported Active. Treat that icon as
unreliable.

## Scripting notes (`system.tag.configure`)

- Collision policy `"m"` (merge) with `"alarms": []` is a **no-op** for removal
  — merge only adds and updates what is supplied — and still returns `[Good]`.
  A successful call is not evidence of a change.
- Policy `"o"` (overwrite) reusing a dict returned by `getConfiguration()`
  fails with `Cannot coerce ... into type: TagPath`: the returned `path` key
  holds a TagPath object that cannot be passed back in. Build a clean config
  dict by hand instead.

## Repeat trigger and full lifecycle

The EMS was restarted (alarm cleared) and stopped again; a second event raised
at 16:53:26. The alarm clears and re-raises rather than latching once.

Timing note: the 12-minute staleness window runs from the **last heartbeat row**
in `ems_decisions`, not from when the service stopped. A restart writes a fresh
heartbeat and resets the clock — restart at 16:41:25 produced the flip at
16:53, not 12 minutes after the 16:43:27 stop.

Acknowledged while Active, then restarted `bess-ems`, giving
`Cleared, Acknowledged`. All four states exercised: raise, acknowledge, clear,
and acknowledgement surviving the clear.

## Alarm Status Table scoped to the `default` provider

The Alarms page was cluttered with Ignition's bundled demo alarms from the
`Sample_Tags` provider. Scoped non-destructively via a component property:

    AlarmStatusTable → props.filters.active.conditions.provider = default

All BESS alarms are in `default`; all demo content is in `Sample_Tags`.
Reversible — clearing the field restores them. Note only the active view is
scoped: `filters.shelved` has no `conditions` node, so demo alarms can still
appear on the Shelved tab. This is a saved project property, unlike the runtime
filter chips, which are per-session.

## Status

- **Step 4 (watchdog alarm on EMS OFFLINE) is complete** and verified against a
  real EMS outage, not a forced one.

## Still open in the panel arc

- Third panel element: live price vs buy/sell thresholds from
  `ems_decisions.reasoning`.
- No Alarm Journal configured — alarm history is memory-only and does not
  survive a gateway restart. Not the cause of this bug; needed only if event
  history has to persist.
