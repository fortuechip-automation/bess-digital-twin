# EMS Heartbeat Fix — Implemented and Verified Live (2026-08-13)

Follow-up to `2026-08-13_panel_and_heartbeat_gap.md`, which found that `ems.py`
goes silent in `ems_decisions` while a manual override is active, causing the
control-mode panel to show a false EMS OFFLINE for a few minutes after every
override expires. This session implements and verifies the fix.

## The fix

`src/ems/ems.py`, override branch (commit `f5e82a8`): the branch previously
wrote one `ems_decisions` row on *detecting* an override (guarded by the
one-shot `override_logged` flag) and then wrote nothing further for the rest
of the hold window, because it hits `continue` on every subsequent poll.

The branch now also checks `last_logged_interval` — the same pointer the
normal (non-override) path already uses to decide whether a new market
interval has started — and writes a repeating `[interval] Manual operator
override active - EMS standing down` row once per interval while the override
persists, same cadence as the regular heartbeat.

```python
if manual_override_active(cur):
    new_interval = now_iv != last_logged_interval
    if not override_logged:
        insert_decision(cur, None, soc, None,
            f"Manual operator command active - EMS standing down "
            f"for {OVERRIDE_HOLD_MIN:.0f} min hold window")
        override_logged = True
        last_logged_interval = now_iv
        last_mode = "IDLE"
        last_p_kw = 0.0
    elif new_interval:
        insert_decision(cur, None, soc, None,
            "[interval] Manual operator override active - EMS standing down")
        last_logged_interval = now_iv
    time.sleep(POLL_SECONDS)
    continue
override_logged = False
```

## Verification (live, bems)

Override triggered 13:26:42. `ems_decisions` confirmed a fresh heartbeat row
at 13:30:03 (the next 5-min interval boundary) reading
`[interval] Manual operator override active - EMS standing down` — the row
that could not exist before the fix. At override expiry (13:41:42) the
control-mode panel lamp went **amber → green directly, no red flash** —
the false-OFFLINE symptom from the prior finding is resolved.

## Status

- Committed on bems as `f5e82a8`, merged with the same-day panel/docs commits
  from the laptop clone (`1a96c2c`), pushed to `main`.
- **Step 4 (watchdog alarm on EMS OFFLINE) is now unblocked** — the heartbeat
  it would monitor stays honest through manual overrides.

## Still open in the panel arc

- Third panel element: live price vs buy/sell thresholds from
  `ems_decisions.reasoning`.
- Step 4: watchdog alarm on EMS OFFLINE.
