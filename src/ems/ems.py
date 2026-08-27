#!/usr/bin/env python3
"""BESS Energy Management System (EMS).

Closes the loop above SCADA: reads site telemetry and a simulated market
price, decides when to charge/discharge (time-of-use arbitrage), writes
site commands to bess_commands, and records every decision with its
reasoning in ems_decisions.

Safety behaviour:
  - Stands down (IDLE) while any CRITICAL alarm is active.
  - Stands down for EMS_OVERRIDE_HOLD_MIN minutes after a manual operator
    command (priority >= 1), so it never fights the SCADA operator.
  - Commands are only written when the decision changes (no command spam).

EMS commands use priority 0; operator commands (via the OPC bridge) use
priority 1, which is how the two are told apart.
"""

import os
import time
from datetime import datetime, timezone

import psycopg2

try:
    from .market import backfill_prices, ensure_market_table, interval_start, upsert_price
    from .strategy import config_from_env, decide
except ImportError:
    from market import backfill_prices, ensure_market_table, interval_start, upsert_price
    from strategy import config_from_env, decide

DB_CONFIG = {
    "host": os.getenv("BESS_DB_HOST", "DB_HOST"),
    "database": os.getenv("BESS_DB_NAME", "bess"),
    "user": os.getenv("BESS_DB_USER", "bessuser"),
    "password": os.getenv("BESS_DB_PASSWORD", "CHANGE_ME"),
    "port": int(os.getenv("BESS_DB_PORT", "5432")),
    "application_name": "bess_ems",
}

POLL_SECONDS = float(os.getenv("EMS_POLL_SECONDS", "10"))
OVERRIDE_HOLD_MIN = float(os.getenv("EMS_OVERRIDE_HOLD_MIN", "15"))
REGION = os.getenv("EMS_REGION", "SIM1")

EMS_PRIORITY = 0  # operator commands from the OPC bridge default to 1


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def connect():
    while True:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.autocommit = True
            log("[DB] Connected")
            return conn
        except Exception as exc:
            log(f"[DB] Connection failed: {exc}. Retrying in 5s...")
            time.sleep(5)


def read_site_soc(cur):
    cur.execute("SELECT soc FROM site_status ORDER BY ts DESC LIMIT 1")
    row = cur.fetchone()
    return float(row[0]) if row else None


def count_critical_alarms(cur) -> int:
    cur.execute(
        "SELECT count(*) FROM bess_alarms WHERE cleared = FALSE AND severity >= 3"
    )
    return int(cur.fetchone()[0])


def manual_override_active(cur) -> bool:
    """True if an operator command arrived within the hold-off window."""
    cur.execute(
        """
        SELECT count(*)
        FROM bess_commands
        WHERE priority >= 1
          AND ts > now() - %s * INTERVAL '1 minute'
        """,
        (OVERRIDE_HOLD_MIN,),
    )
    return int(cur.fetchone()[0]) > 0


def last_ems_mode(cur) -> str:
    cur.execute(
        """
        SELECT mode_set FROM bess_commands
        WHERE priority = %s
        ORDER BY ts DESC LIMIT 1
        """,
        (EMS_PRIORITY,),
    )
    row = cur.fetchone()
    return row[0].upper() if row else "IDLE"


def insert_command(cur, mode: str, p_kw: float) -> int:
    cur.execute(
        """
        INSERT INTO bess_commands (ts, p_set_kw, mode_set, priority, processed)
        VALUES (now(), %s, %s, %s, FALSE)
        RETURNING command_id
        """,
        (p_kw, mode, EMS_PRIORITY),
    )
    return int(cur.fetchone()[0])


def last_operator_command(cur):
    """The newest operator (priority >= 1) command, as (mode, p_kw).

    Used at override handover: while the EMS stands down, THIS is what the
    plant is executing, and it will keep executing it until someone says
    otherwise.
    """
    cur.execute(
        """
        SELECT mode_set, p_set_kw FROM bess_commands
        WHERE priority >= 1
        ORDER BY ts DESC LIMIT 1
        """
    )
    row = cur.fetchone()
    return (row[0].upper(), abs(float(row[1]))) if row else ("IDLE", 0.0)


def insert_decision(cur, command_fk, soc, target_soc, reasoning) -> None:
    cur.execute(
        """
        INSERT INTO ems_decisions (ts, command_fk, current_soc, target_soc, reasoning)
        VALUES (now(), %s, %s, %s, %s)
        """,
        (command_fk, soc, target_soc, reasoning),
    )


def main() -> None:
    cfg = config_from_env()
    log(f"[EMS] Starting - buy<{cfg.charge_below} sell>{cfg.discharge_above} $/MWh, "
        f"SOC {cfg.soc_min}-{cfg.soc_max}%, override hold {OVERRIDE_HOLD_MIN} min")

    conn = connect()
    with conn.cursor() as cur:
        ensure_market_table(cur)
        added = backfill_prices(cur, hours=24, region=REGION)
        if added:
            log(f"[MARKET] Backfilled {added} price intervals")

    last_mode = "IDLE"
    last_p_kw = 0.0
    last_logged_interval = None
    override_logged = False

    with conn.cursor() as cur:
        last_mode = last_ems_mode(cur)
        log(f"[EMS] Resuming with last EMS mode: {last_mode}")

    while True:
        try:
            with conn.cursor() as cur:
                now_iv = interval_start(datetime.now(timezone.utc))
                price = upsert_price(cur, now_iv, REGION)
                soc = read_site_soc(cur)
                if soc is None:
                    log("[EMS] No site telemetry yet - waiting")
                    time.sleep(POLL_SECONDS)
                    continue

                critical = count_critical_alarms(cur)

                if manual_override_active(cur):
                    new_interval = now_iv != last_logged_interval
                    if not override_logged:
                        insert_decision(
                            cur, None, soc, None,
                            f"Manual operator command active - EMS standing down "
                            f"for {OVERRIDE_HOLD_MIN:.0f} min hold window",
                        )
                        log("[EMS] Manual override detected - standing down")
                        override_logged = True
                        last_logged_interval = now_iv
                        # Adopt the OPERATOR's command as our last-known state, not
                        # IDLE/0. The plant is executing their setpoint and will keep
                        # executing it until someone commands otherwise -- so that,
                        # not a convenient fiction about ourselves, is what the next
                        # decision must be compared against when the hold lapses.
                        # Setting IDLE/0 here made the EMS believe the plant was
                        # already at rest, so a dead-band "IDLE 0 kW" decision looked
                        # like no change and no command was ever sent.
                        # (Found live 2026-08-27: operator CHARGE 15 kW at 15:42,
                        #  override lapsed 15:57, EMS decided "holding" at 16:00,
                        #  16:05 and 16:10 while the battery charged on regardless.)
                        last_mode, last_p_kw = last_operator_command(cur)
                    elif new_interval:
                        insert_decision(
                            cur, None, soc, None,
                            "[interval] Manual operator override active - EMS standing down",
                        )
                        last_logged_interval = now_iv
                    time.sleep(POLL_SECONDS)
                    continue
                override_logged = False

                decision = decide(soc, price, last_mode, cfg, critical)

                changed = (
                    decision.mode != last_mode
                    or abs(decision.p_kw - last_p_kw) > 1.0
                )
                new_interval = now_iv != last_logged_interval

                if changed:
                    cmd_id = insert_command(cur, decision.mode, decision.p_kw)
                    insert_decision(
                        cur, cmd_id, soc, decision.target_soc, decision.reasoning
                    )
                    log(f"[EMS] {decision.mode} {decision.p_kw:.0f} kW "
                        f"(cmd {cmd_id}) - {decision.reasoning}")
                    last_mode = decision.mode
                    last_p_kw = decision.p_kw
                    last_logged_interval = now_iv
                elif new_interval:
                    insert_decision(
                        cur, None, soc, decision.target_soc,
                        f"[interval] {decision.reasoning}",
                    )
                    last_logged_interval = now_iv

        except psycopg2.Error as exc:
            log(f"[DB] Error: {exc}. Reconnecting...")
            try:
                conn.close()
            except Exception:
                pass
            conn = connect()

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
