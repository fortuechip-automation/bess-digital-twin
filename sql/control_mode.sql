-- Control-mode derivation for the Ignition control-mode panel.
-- Returns exactly one row: control_mode = MANUAL | AUTO | EMS OFFLINE.
--
-- Precedence is encoded by CASE order (first true branch wins):
--   1. MANUAL      — an operator command (priority >= 1) younger than 15 min.
--                    This is deliberately the same predicate as
--                    manual_override_active() in src/ems/ems.py
--                    (EMS_OVERRIDE_HOLD_MIN), so the panel and the EMS can
--                    never disagree about who is in control.
--   2. AUTO        — EMS heartbeat is fresh. The EMS writes an ems_decisions
--                    row at least once per 5-min market interval; 12 min
--                    means two missed intervals plus slack.
--   3. EMS OFFLINE — neither: the heartbeat is stale (or has never beaten;
--                    max(ts) over an empty table is NULL, NULL comparisons
--                    are never true, and the ELSE catches it).
--
-- Design decision 2026-08-12: MANUAL outranks EMS OFFLINE. The lamp answers
-- "who is driving right now"; EMS health belongs to the step-4 watchdog alarm.

SELECT CASE
    WHEN (SELECT count(*) FROM bess_commands
          WHERE priority >= 1
            AND ts > now() - INTERVAL '15 minutes') > 0
        THEN 'MANUAL'
    WHEN (SELECT max(ts) FROM ems_decisions) > now() - INTERVAL '12 minutes'
        THEN 'AUTO'
    ELSE 'EMS OFFLINE'
END AS control_mode;
