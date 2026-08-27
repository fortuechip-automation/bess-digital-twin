# EMS left expired operator commands running on the plant (2026-08-27)

**Status:** root cause identified, fixed, verified live.
**Files touched:** `src/ems/ems.py`, `sql/active_setpoint.sql` (new), Ignition project
(Named Query `ActiveSetpoint`, `BESS1_MainPage` → `kpiPSet/lblPSetValue` binding).

## Symptom

Found 2026-08-26 (bess-viz session): after a manual override lapsed, the SCADA panel
showed `P SET 15 kW` next to `ACTUAL MODE: IDLE` while `site_status.p_set_kw` read 0.0.

Investigating that display defect uncovered a second, more serious one: on some
handovers the *plant itself* kept executing the expired operator command.

## Evidence

`site_status` tracks whoever is in control (verified live: operator CHARGE 15 kW at
15:42:11 appears as `mode` 1→2, `p_set_kw` 0.0→15.0, `p_actual_kw` → 14.99).

Operator command 15:42, override window expires 15:57. At 16:11:48 the plant was still
at `p_set = 15.00`, `p_actual = 15.01`, `mode = 2`. `ems_decisions` over that window:

    15:55:02  [interval] Manual operator override active - EMS standing down
    16:00:03  [interval] Price 90.2 $/MWh in dead band (40-120 $/MWh) - holding
    16:05:05  [interval] Price 87.4 $/MWh in dead band (40-120 $/MWh) - holding
    16:10:06  [interval] Price 95.2 $/MWh in dead band (40-120 $/MWh) - holding

The EMS was alive (heartbeat ~1 min old), back in control from 15:57, and decided
"holding" three times while the battery charged. All rows `command_fk = NULL`.

## Root cause

`strategy.py` is correct: the dead band returns `Decision("IDLE", 0.0, ...)`.

`ems.py`, on detecting a manual override, re-synced its own last-known state to a value
it invented:

    # Re-sync so hysteresis restarts cleanly after the hold.
    last_mode = "IDLE"
    last_p_kw = 0.0

On the first cycle after the window lapsed:

    decision = decide(soc, price, last_mode, cfg, critical)   # dead band -> IDLE, 0.0
    changed = (decision.mode != last_mode                     # "IDLE" != "IDLE" -> False
               or abs(decision.p_kw - last_p_kw) > 1.0)       # |0.0 - 0.0|      -> False

`changed` is False, so no command is written and the inverter keeps executing whatever
was last written to it.

The EMS compared its new decision against a state it had invented about *itself* during
the stand-down. Generalised: **the EMS treated "no command" as equivalent to "idle."**
That holds only while the EMS is the sole writer of the setpoint. Once a second writer
exists (the operator via the OPC bridge), silence no longer means rest. This is
edge-triggered control where the situation demands level-triggered.

## Falsifiable prediction (made before the test)

> Override expires 16:26:49. The next interval row will read `Price ... in dead band -
> holding` with `command_fk = NULL`; `p_set` will remain 15.00; the mode lamp will flip
> to AUTO while nothing about the plant changes.

Held: `p_set` still 15.00 at 16:27.

## Fix

New helper in `ems.py`:

    def last_operator_command(cur):
        """The newest operator (priority >= 1) command, as (mode, p_kw)."""
        cur.execute(
            """
            SELECT mode_set, p_set_kw FROM bess_commands
            WHERE priority >= 1
            ORDER BY ts DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        return (row[0].upper(), abs(float(row[1]))) if row else ("IDLE", 0.0)

and in the override branch, replacing `last_mode = "IDLE"; last_p_kw = 0.0`:

    last_mode, last_p_kw = last_operator_command(cur)

At handover the comparison is now `IDLE` vs `CHARGE` and `0.0` vs `15.0`, so `changed`
is True and `insert_command(cur, "IDLE", 0.0)` fires.

`abs()` on `p_set_kw` is defensive: `bess_commands.p_set_kw` is documented as an
unsigned magnitude with direction in `mode_set`, but the Grafana convention elsewhere is
negative-kW-means-discharge. **Not yet verified against a real operator DISCHARGE
command** — worth confirming.

## Verification (live, 2026-08-27)

Plant:

    16:59:53  mode=2  p_set=  15.00  p_actual=  14.99
    16:59:55  mode=1  p_set=   0.00  p_actual=   0.00

`ems_decisions`:

    5970  16:59:53  command_fk=262615  'Price 113.5 $/MWh in dead band - holding'
    5971  17:00:03  command_fk=NULL    '[interval] Price 117.0 $/MWh in dead band - holding'

Row 5970 has a real `command_fk` and no `[interval]` prefix — the `changed` branch. Row
5971 shows the EMS going quiet again immediately after: one command on handover, not
command spam, because `last_mode`/`last_p_kw` are now truthful.

The reclaim fired at 16:59:55 — command time + 15:00, on the first poll after the window
closed — not on a 5-minute market-interval boundary. Override clock, as designed.

## Companion display fix

`sql/active_setpoint.sql` (new) → Ignition Named Query `ActiveSetpoint` (Scalar,
`BESS_Database`):

    SELECT CASE
        WHEN ts > now() - INTERVAL '10 seconds' THEN p_set_kw
        ELSE NULL
    END AS active_setpoint_kw
    FROM site_status
    ORDER BY ts DESC
    LIMIT 1

`BESS1_MainPage` → `kpiPSet/lblPSetValue`: `props.text` moved from a Tag binding on
`[default]BESS1/Site/P_set_kW` to a Query binding on `ActiveSetpoint` (poll 1 s) with an
Expression transform `if(isNull({value}), "—", numberFormat({value}, "0.##"))`.

The 10-second staleness guard is load-bearing: binding to "newest row" alone would
re-create the same defect one layer down if the simulator stopped. NULL renders as a
dash — "we do not currently know" — rather than a confident dead number.

Trade-off: Tag binding = subscription (push); Query binding = poll. Instant updates
given up for a source that tells the truth; consistent with the mode lamp (10 s) and
override countdown (1 s).

Note: the binding fails with `Named query "ActiveSetpoint" not found` until the Ignition
project is **saved** — bindings resolve against the gateway's saved project, while the
Named Query Testing tab runs the local Designer session.

## Open items

- `bess_commands.p_set_kw` sign convention unverified for operator DISCHARGE commands.
- SOC reached 90.76% against `soc_max = 90.0`: a manual override bypasses the EMS SOC
  guard bands. Correct authority hierarchy, but the ceiling is only enforced by the
  layer an operator may overrule. On a real site this belongs in the BMS.
- The 15-minute override window is duplicated in three places: `EMS_OVERRIDE_HOLD_MIN`
  (`ems.py`) and hard-coded `INTERVAL '15 minutes'` in `control_mode.sql` and
  `override_seconds_left.sql`. `control_mode.sql`'s comment claims the predicate is
  identical "so the panel and the EMS can never disagree" — but it is a copy, not a
  shared source. Changing one desynchronises them silently.
- Deeper fix: level-triggered reconciliation — read the plant's actual setpoint from
  `site_status` each cycle and command whenever intent and reality differ, instead of
  tracking any belief about the plant. Same requirement a PPC has.
