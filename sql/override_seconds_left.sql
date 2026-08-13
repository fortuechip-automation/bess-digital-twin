-- Seconds remaining in the manual override window; 0 when no override is active.
-- Used by the Ignition Named Query "OverrideSecondsLeft" (control-mode panel
-- countdown). Same 15-minute window as control_mode.sql and
-- manual_override_active() in src/ems/ems.py — the panel does presentation
-- only; the window arithmetic lives here, next to the predicate.
--
--   max(ts)                : the newest operator (priority >= 1) command
--   + INTERVAL '15 minutes': when that override expires
--   - now()                : time remaining (negative once expired)
--   EXTRACT(EPOCH FROM ..) : interval -> plain seconds, so the panel gets a number
--   GREATEST(0, ..)        : clamps expired negatives to 0; also covers the
--                            never-any-commands case (max = NULL, and Postgres
--                            GREATEST ignores NULLs, so this still returns 0).

SELECT GREATEST(
    0,
    EXTRACT(EPOCH FROM (max(ts) + INTERVAL '15 minutes' - now()))
)::int AS override_seconds_left
FROM bess_commands
WHERE priority >= 1;
