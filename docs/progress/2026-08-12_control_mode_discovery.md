# Control-Mode Panel — Discovery Findings (2026-08-12)

Groundwork for an Ignition control-mode panel showing AUTO / MANUAL / EMS OFFLINE.
This session established where "who is in control" actually lives in the database.
No code changes; findings below drive the panel design.

## Command provenance (census of `bess_commands`, 2026-08-12)

| priority | source_ip   | count   | first_seen | last_seen  | writer                        |
|----------|-------------|---------|------------|------------|-------------------------------|
| 0        | NULL        | 1,855   | 2026-07-03 | 2026-07-23 | EMS (matches `ems_decisions`) |
| 1        | 127.0.0.1   | 6       | 2026-05-20 | 2026-05-25 | manual curl tests on bems     |
| 1        | 172.20.0.30 | 130     | 2025-12-09 | 2026-05-11 | Ignition operator commands    |
| 1        | 172.20.0.20 | 259,972 | 2026-05-13 | 2026-08-10 | **bsim — unidentified, ~1 row / 30 s while sim runs** |
| 1        | NULL        | 11      | 2025-11-17 | 2025-11-28 | early-lab leftovers           |

## Facts the panel design must respect

- **EMS fingerprint:** `priority = 0`, `source_ip IS NULL`. The EMS stamps priority 0
  explicitly; the column default is 1.
- **Operator fingerprint:** `source_ip = '172.20.0.30'` (Ignition/bscada). Priority alone
  is NOT a human marker — see next point.
- **The naive rule "recent priority-1 command ⇒ MANUAL" is broken:** something on bsim
  (172.20.0.20) writes a priority-1 command every ~30 s whenever the simulator stack is
  running. A panel using that rule would show MANUAL permanently.
- **EMS heartbeat:** `ems_decisions.ts` gains a row every EMS cycle; `command_fk` is NULL
  on "no change" cycles (~262k decisions vs 1,855 commands). Staleness of this table is
  the EMS-OFFLINE signal — last row currently 2026-07-23 because the service hasn't run
  since.
- `ems_decisions.reasoning` already contains the price-vs-threshold explanation per cycle —
  usable directly for a "why is the EMS doing this" display.

## Open questions (next session)

1. How does the EMS's own stand-down logic distinguish a real operator override from the
   bsim command stream? (It charged on 2026-07-23 while the stream was active, so it does.)
   Read `ems.py` / `strategy.py`; the panel's MANUAL rule must match the EMS's rule.
2. Identify the bsim writer (suspect: OPC bridge echoing setpoints — unverified).
3. Write the derived-mode query: MANUAL / AUTO / EMS OFFLINE.
