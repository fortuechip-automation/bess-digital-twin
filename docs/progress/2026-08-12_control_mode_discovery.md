# Control-Mode Panel — Discovery Findings (2026-08-12)

Groundwork for an Ignition control-mode panel showing AUTO / MANUAL / EMS OFFLINE.
This session established where "who is in control" actually lives in the database.

> **Revised same day:** the first version of this doc called the bsim command stream an
> ongoing flood and proposed source_ip as the human fingerprint. Both claims were wrong;
> a per-week histogram and a read of the bridge/EMS source corrected them. See git
> history for the original.

## Command provenance (census of `bess_commands`, 2026-08-12)

| priority | source_ip   | count   | when                  | writer                                  |
|----------|-------------|---------|-----------------------|------------------------------------------|
| 0        | NULL        | 1,855   | 2026-07-03 → 07-23    | EMS (stamps priority 0 explicitly)       |
| 1        | 127.0.0.1   | 6       | 2026-05-20 → 05-25    | manual curl tests against the API        |
| 1        | 172.20.0.30 | 130     | 2025-12-09 → 2026-05-11 | Ignition direct-DB command era (ended)  |
| 1        | 172.20.0.20 | 259,972 | 2026-05-13 → ongoing  | OPC bridge — see breakdown below         |
| 1        | NULL        | 11      | 2025-11 only          | early-lab leftovers                      |

### The 172.20.0.20 pile is two very different things

Per-week histogram: **259,879 of the 259,972 rows fall in the week of 2026-06-01.**
That burst is the ApplyCommand reset-spam bug — introduced around b73ffaa (2026-06-02,
"Require explicit apply"), inserting once per bridge poll (1 s) for ~72 h, killed by
d5e6835 (2026-06-05, "Fix ApplyCommand reset spam"). It is a fossil, not a live behaviour.

Everything since 2026-06-05 is a thin trickle (1–14 rows/week): genuine operator
commands via the current path **Ignition → OPC `ApplyCommand` pulse → bridge insert**.
The bridge stamps its own address (BESS_OPC_SOURCE_IP = 172.20.0.20) and omits
`priority`, taking the column default 1.

## Facts the panel design must respect

- **EMS fingerprint:** `priority = 0` (set explicitly in `ems.py`; `source_ip` NULL).
- **Operator fingerprint:** `priority >= 1` — priority, not source_ip, is the signal.
  Since 2026-06-05 nothing non-human writes priority-1 rows.
- **The EMS's own arbitration** (`ems.py`, `manual_override_active()`): stand down if any
  `priority >= 1` command is younger than `EMS_OVERRIDE_HOLD_MIN` (15 min). The panel's
  MANUAL rule must be this exact predicate so panel and EMS never disagree.
- **Recorded assumption:** if a rogue priority-1 writer (like the June spam bug) ever
  returns, it silently disables the EMS *and* pins the panel to MANUAL. A rate sanity
  check (priority-1 commands/hour) would catch it.
- **EMS heartbeat:** `ems_decisions` gains a row at least once per 5-min market interval
  while the EMS runs (`command_fk` NULL on no-change cycles). Staleness beyond ~2
  intervals = EMS OFFLINE. Last row currently 2026-07-23 (service not started since).
- `ems_decisions.reasoning` carries the per-cycle price-vs-threshold explanation —
  directly usable for the panel's "why" display.

## Next session

1. Decide precedence when both conditions hold (fresh manual command + stale heartbeat):
   MANUAL or EMS OFFLINE?
2. Write the derived-mode query (MANUAL / AUTO / EMS OFFLINE) using the exact
   `manual_override_active` predicate; parameterise the 15-min hold to match
   `EMS_OVERRIDE_HOLD_MIN`.
3. Then step 3: bind it into an Ignition panel (mode lamp, override countdown, live
   price vs thresholds from `reasoning`).
