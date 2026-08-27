-- The setpoint currently IN FORCE, for the Ignition control-mode panel.
--
-- site_status is the plant's own 1 Hz record of what it has been commanded to do, and
-- it tracks whoever is in control -- the EMS in AUTO, the operator during a manual
-- override. Verified live 2026-08-27: an operator CHARGE 15 kW from Ignition appears
-- here at 15:42:11 as mode 1->2 and p_set_kw 0.0 -> 15.0, with p_actual_kw following to
-- 14.99, and returns to 0.0 when the EMS reclaims the plant at handover.
--
-- Why this exists (found 2026-08-26): the OPC tag BESS1/Site/P_set_kW keeps whatever was
-- last written to it and nothing clears it on handover, so after an override lapsed the
-- panel read "P SET 15 kW" beside "ACTUAL MODE: IDLE" while the database correctly said
-- 0.0. Two numbers on one screen, and an operator having to guess which to believe.
-- Rule: never display a commanded value that is not in force.
--
-- The staleness guard is the point, not a detail. Binding to "newest row" alone would
-- re-create that same defect one layer down: if the simulator stops, the newest row
-- stops moving and the panel would display a dead value forever. Same reasoning as the
-- 12-minute heartbeat window in control_mode.sql -- at 1 Hz, 10 seconds is ten missed
-- rows, well beyond jitter and nowhere near a plausible live gap. NULL means "we do not
-- currently know", and the panel shows a dash.
--
-- ORDER BY with the LIMIT is deliberate: a LIMIT without one returns an arbitrary row
-- and will happily serve stale data (see the Grafana Active-Alarms trap, 2026-08-06).
--
-- Used by the Ignition Named Query "ActiveSetpoint" (Scalar, BESS_Database), bound to
-- BESS1_MainPage -> kpiPSet/lblPSetValue props.text with a 1 s poll and an Expression
-- transform: if(isNull({value}), "—", numberFormat({value}, "0.##"))

SELECT CASE
    WHEN ts > now() - INTERVAL '10 seconds' THEN p_set_kw
    ELSE NULL
END AS active_setpoint_kw
FROM site_status
ORDER BY ts DESC
LIMIT 1
