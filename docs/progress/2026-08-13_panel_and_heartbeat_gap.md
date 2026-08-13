# Control-Mode Panel Built + EMS Heartbeat Gap Found (2026-08-13)

Step 3 of the control-mode panel arc: the Ignition panel now exists and is verified
live in all three states. The test run also exposed a real gap in the EMS's
heartbeat behaviour that blocks the step-4 watchdog until fixed.

## What was built (Perspective, BESS1_MainPage)

- **Named Query `ControlMode`** — `sql/control_mode.sql` verbatim, via the gateway's
  existing `BESS_Database` connection (a survivor of the direct-DB era; reads only,
  commands still flow Ignition → OPC ApplyCommand → bridge).
- **Mode lamp** — Label, query binding on `props.text` (scalar, 10 s polling);
  `style.backgroundColor` property-bound to its own text through a Map transform:
  AUTO → green `#2E7D32`, MANUAL → amber `#FF8F00`, EMS OFFLINE → red `#C62828`,
  fallback gray `#757575` (unknown must look like ignorance, not health).
- **Named Query `OverrideSecondsLeft`** — new, `sql/override_seconds_left.sql`:
  seconds left in the 15-min override window, computed in SQL next to the same
  predicate so the window is never duplicated in the panel.
- **Countdown label** — query binding (scalar, 1 s polling) + expression transform
  formatting `m:ss`; renders an empty string at 0, so it only appears during an
  active override.

Verified live: AUTO on open; amber within one poll of a priority-1 insert;
countdown ticking from 14:5x; at expiry amber → red → green (see below — the red
blip was predicted in advance and is meaningful).

## The find: the EMS heartbeat goes silent during stand-down

Observed during the MANUAL test:

- `ems_decisions` heartbeat age reached **11:35 while the override was ~11.5 min
  old** — the last row landed at the moment the operator command did.
- **`ems.py` writes no `ems_decisions` rows while `manual_override_active()` is
  true.** The at-least-per-5-min heartbeat only holds while the EMS is actively
  driving.
- Consequence, reproduced on the panel: the instant a manual override expires, the
  heartbeat is ~15 min stale, so the lamp shows **EMS OFFLINE for a few minutes**
  until the EMS resumes and writes its next row — a false OFFLINE while the
  process is alive and healthy.

The panel is not at fault: from its evidence, a silent EMS and a dead EMS are
indistinguishable. The fix belongs in the EMS.

## Action queued (blocks step 4)

**`ems.py` should log stand-down as a decision** — one `ems_decisions` row per
interval during an override (reasoning: standing down for operator override,
`command_fk` NULL), keeping the heartbeat honest while yielding control. Until
then, the step-4 watchdog alarm on heartbeat staleness would false-alarm after
every manual override. Planned as the next EMS code lesson (level 2/3 edits).

## Still open in the panel arc

- Third panel element: live price vs buy/sell thresholds from
  `ems_decisions.reasoning`.
- Step 4: watchdog alarm on EMS OFFLINE (after the heartbeat fix).
