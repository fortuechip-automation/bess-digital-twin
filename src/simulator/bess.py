#!/usr/bin/env python3
"""
BESS Fleet Simulator (Realistic Multi-Device, DB-Optimized)

Simulates:
  - 10 inverters (inverter_id 1..10)
  - 20 batteries  (battery_id 1..20)

DB Tables (already exist in your DB):
  - site_status      (1 row/sec)
  - inverter_status  (10 rows/sec)
  - battery_status   (20 rows/sec)
  - bess_alarms      (alarms)

Commands:
  - reads from bess_commands (site-level command)

Optimizations:
  - single DB connection + cursor (centralized)
  - execute_values() for fast batch inserts
  - rounding before insert (cleaner DB values)
  - site shortfall alarm if setpoint not met for >5 seconds

FIX INCLUDED:
  - Site mode is derived from ACTUAL site power (p_actual_site) AFTER the loop,
    so Site Mode matches inverter/battery behavior without crashing.
"""

import time
import random
import os
from datetime import datetime
from typing import Tuple

import psycopg2
from psycopg2.extras import execute_values

try:
    from .fleet import BESSFleet
except ImportError:
    from fleet import BESSFleet

# =========================================================
#  DB CONFIG
# =========================================================
DB_CONFIG = {
    "host": os.getenv("BESS_DB_HOST", "DB_HOST"),
    "database": os.getenv("BESS_DB_NAME", "bess"),
    "user": os.getenv("BESS_DB_USER", "bessuser"),
    "password": os.getenv("BESS_DB_PASSWORD", "CHANGE_ME"),
    "port": int(os.getenv("BESS_DB_PORT", "5432")),
}

# =========================================================
#  FLEET CONFIG
# =========================================================
N_INVERTERS = 10
N_BATTERIES = 20

def inv_to_bats(inv_index_zero_based: int) -> Tuple[int, int]:
    """INV01->BAT01,BAT02 ; INV02->BAT03,BAT04 ..."""
    b1 = 2 * inv_index_zero_based
    b2 = 2 * inv_index_zero_based + 1
    return b1, b2

# =========================================================
#  MODEL CONSTANTS
# =========================================================
TELEMETRY_INTERVAL = 1.0

# Total site capacity (split equally into 20 batteries)
SITE_CAPACITY_KWH = 1000.0

# Site power limits (AC)
SITE_MAX_CHARGE_KW = 250.0
SITE_MAX_DISCHARGE_KW = -250.0

# Component limits
INV_MAX_KW = 250.0
BAT_MAX_KW = 150.0

# Efficiencies
BAT_ROUNDTRIP_EFF = 0.95
INV_EFF = 0.97

# =========================================================
#  ALARM THRESHOLDS
# =========================================================
ALARM_THRESHOLDS = {
    "soc_critical_low": 5.0,
    "soc_low": 10.0,
    "soc_high": 90.0,
    "soc_critical_high": 95.0,
    "temp_warning": 35.0,
    "temp_critical": 45.0,
    "voltage_low": 750.0,
    "voltage_high": 850.0,
    "current_warning": 300.0,
    "current_critical": 350.0,
    # Site shortfall logic
    "site_shortfall_kw": 5.0,     # trigger if |P_set - P_actual| > this...
    "site_shortfall_secs": 5,     # ...for this many consecutive seconds
}

SEVERITY = {"INFO": 1, "WARNING": 2, "CRITICAL": 3, "FAULT": 4}

MODE_IDLE = 1
MODE_CHARGE = 2
MODE_DISCHARGE = 3

def map_mode_id_to_text(mode_id: int) -> str:
    if mode_id == MODE_IDLE:
        return "IDLE"
    if mode_id == MODE_CHARGE:
        return "CHARGE"
    if mode_id == MODE_DISCHARGE:
        return "DISCHARGE"
    return "UNKNOWN"

def mode_from_setpoint(p_kw: float) -> int:
    # deadband around zero to avoid mode flicker
    if abs(p_kw) < 0.5:
        return MODE_IDLE
    return MODE_CHARGE if p_kw > 0 else MODE_DISCHARGE

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def r2(x: float) -> float:
    """Round for cleaner DB values."""
    return float(round(x, 2))

# =========================================================
#  SIMULATION STATE
# =========================================================
p_set_kw = 0.0
op_mode_id = MODE_IDLE
last_processed_command_id = 0

# site shortfall debounce counter
site_shortfall_counter = 0

# Active alarms (site-level)
active_alarms = set()

# Batteries
battery_soc = [50.0 + random.uniform(-2, 2) for _ in range(N_BATTERIES)]
battery_fault = [False for _ in range(N_BATTERIES)]

# Inverters
inverter_fault = [False for _ in range(N_INVERTERS)]

# Modular fleet model. The DB/command/alarm runtime still lives in this file,
# but the simulation calculation is delegated to BESSFleet.
fleet = BESSFleet()

# =========================================================
#  DB: CENTRALIZED CONNECTION
# =========================================================
def get_connection():
    while True:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.autocommit = False
            return conn
        except Exception as e:
            print(f"[DB] Connection failed: {e}. Retrying in 3s...")
            time.sleep(3)

# =========================================================
#  ALARM TABLE INIT
# =========================================================
def init_alarm_table(cur):
    sql = """
        CREATE TABLE IF NOT EXISTS bess_alarms (
            alarm_id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ DEFAULT NOW(),
            alarm_code TEXT NOT NULL,
            severity SMALLINT NOT NULL,
            message TEXT,
            value REAL,
            threshold REAL,
            cleared BOOLEAN DEFAULT FALSE,
            cleared_ts TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS idx_bess_alarms_ts ON bess_alarms(ts);
        CREATE INDEX IF NOT EXISTS idx_bess_alarms_code ON bess_alarms(alarm_code);
        CREATE INDEX IF NOT EXISTS idx_bess_alarms_active ON bess_alarms(cleared) WHERE cleared = FALSE;
    """
    cur.execute(sql)
    print("[INIT] Alarm table initialized")

# =========================================================
#  ALARM MANAGEMENT (CENTRALIZED CURSOR)
# =========================================================
def log_alarm(cur, alarm_code, severity_name, message, value=None, threshold=None):
    severity_level = SEVERITY.get(severity_name, SEVERITY["INFO"])
    sql = """
        INSERT INTO bess_alarms (ts, alarm_code, severity, message, value, threshold)
        VALUES (NOW(), %s, %s, %s, %s, %s)
        RETURNING alarm_id;
    """
    cur.execute(sql, (alarm_code, severity_level, message, value, threshold))
    alarm_id = cur.fetchone()[0]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  ALARM [{severity_name}] → {alarm_code}: {message}")
    return alarm_id

def log_event(cur, event_code, message, value=None, threshold=None):
    """Record a non-alarm event without making it appear active in SCADA."""
    severity_level = SEVERITY["INFO"]
    sql = """
        INSERT INTO bess_alarms
        (ts, alarm_code, severity, message, value, threshold, cleared, cleared_ts)
        VALUES (NOW(), %s, %s, %s, %s, %s, TRUE, NOW())
        RETURNING alarm_id;
    """
    cur.execute(sql, (event_code, severity_level, message, value, threshold))
    event_id = cur.fetchone()[0]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] EVENT → {event_code}: {message}")
    return event_id

def clear_alarm(cur, alarm_code):
    sql = """
        UPDATE bess_alarms
        SET cleared = TRUE, cleared_ts = NOW()
        WHERE alarm_code = %s AND cleared = FALSE;
    """
    cur.execute(sql, (alarm_code,))
    cleared_count = cur.rowcount
    if cleared_count:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ ALARM CLEARED → {alarm_code}")
    return cleared_count

def load_active_alarms(cur):
    sql = """
        SELECT DISTINCT alarm_code
        FROM bess_alarms
        WHERE cleared = FALSE
          AND severity > %s;
    """
    cur.execute(sql, (SEVERITY["INFO"],))
    active_alarms.clear()
    active_alarms.update(row[0] for row in cur.fetchall())
    if active_alarms:
        print(f"[INIT] Loaded active alarms from DB: {', '.join(sorted(active_alarms))}")

def check_and_log_alarm(cur, alarm_code, condition, severity_name, message, value=None, threshold=None):
    if condition:
        if alarm_code not in active_alarms:
            log_alarm(cur, alarm_code, severity_name, message, value, threshold)
            active_alarms.add(alarm_code)
        return True
    else:
        clear_alarm(cur, alarm_code)
        active_alarms.discard(alarm_code)
        return False

# =========================================================
#  ALARM CHECKS (SITE LEVEL)
# =========================================================
def check_all_alarms(cur, soc, temp_c, v_dc_bus, current_a, p_set_kw_in, p_actual_kw_in):
    # SOC
    check_and_log_alarm(
        cur, "SOC_CRITICAL_LOW",
        soc <= ALARM_THRESHOLDS["soc_critical_low"],
        "CRITICAL", f"Site SOC critically low: {soc:.1f}%", soc, ALARM_THRESHOLDS["soc_critical_low"]
    )
    check_and_log_alarm(
        cur, "SOC_LOW",
        (soc <= ALARM_THRESHOLDS["soc_low"]) and (soc > ALARM_THRESHOLDS["soc_critical_low"]),
        "WARNING", f"Site SOC low: {soc:.1f}%", soc, ALARM_THRESHOLDS["soc_low"]
    )
    check_and_log_alarm(
        cur, "SOC_CRITICAL_HIGH",
        soc >= ALARM_THRESHOLDS["soc_critical_high"],
        "CRITICAL", f"Site SOC critically high: {soc:.1f}%", soc, ALARM_THRESHOLDS["soc_critical_high"]
    )
    check_and_log_alarm(
        cur, "SOC_HIGH",
        (soc >= ALARM_THRESHOLDS["soc_high"]) and (soc < ALARM_THRESHOLDS["soc_critical_high"]),
        "WARNING", f"Site SOC high: {soc:.1f}%", soc, ALARM_THRESHOLDS["soc_high"]
    )

    # Temperature
    check_and_log_alarm(
        cur, "TEMP_CRITICAL",
        temp_c >= ALARM_THRESHOLDS["temp_critical"],
        "CRITICAL", f"Site temperature critical: {temp_c:.1f}°C", temp_c, ALARM_THRESHOLDS["temp_critical"]
    )
    check_and_log_alarm(
        cur, "TEMP_WARNING",
        (temp_c >= ALARM_THRESHOLDS["temp_warning"]) and (temp_c < ALARM_THRESHOLDS["temp_critical"]),
        "WARNING", f"Site temperature elevated: {temp_c:.1f}°C", temp_c, ALARM_THRESHOLDS["temp_warning"]
    )

    # Voltage
    check_and_log_alarm(
        cur, "VOLTAGE_LOW",
        v_dc_bus < ALARM_THRESHOLDS["voltage_low"],
        "WARNING", f"DC bus voltage low: {v_dc_bus:.1f}V", v_dc_bus, ALARM_THRESHOLDS["voltage_low"]
    )
    check_and_log_alarm(
        cur, "VOLTAGE_HIGH",
        v_dc_bus > ALARM_THRESHOLDS["voltage_high"],
        "WARNING", f"DC bus voltage high: {v_dc_bus:.1f}V", v_dc_bus, ALARM_THRESHOLDS["voltage_high"]
    )

    # Current
    abs_current = abs(current_a)
    check_and_log_alarm(
        cur, "CURRENT_CRITICAL",
        abs_current >= ALARM_THRESHOLDS["current_critical"],
        "CRITICAL", f"Site current critical: {abs_current:.1f}A", abs_current, ALARM_THRESHOLDS["current_critical"]
    )
    check_and_log_alarm(
        cur, "CURRENT_WARNING",
        (abs_current >= ALARM_THRESHOLDS["current_warning"]) and (abs_current < ALARM_THRESHOLDS["current_critical"]),
        "WARNING", f"Site current elevated: {abs_current:.1f}A", abs_current, ALARM_THRESHOLDS["current_warning"]
    )

    # Operational
    check_and_log_alarm(
        cur, "CHARGE_AT_HIGH_SOC",
        soc >= 95.0 and p_set_kw_in > 0,
        "WARNING", f"Charging attempted at {soc:.1f}% SOC", soc, 95.0
    )
    check_and_log_alarm(
        cur, "DISCHARGE_AT_LOW_SOC",
        soc <= 5.0 and p_set_kw_in < 0,
        "WARNING", f"Discharging attempted at {soc:.1f}% SOC", soc, 5.0
    )

    # POWER_LIMITED (instant, informational)
    power_diff = abs(p_set_kw_in - p_actual_kw_in)
    check_and_log_alarm(
        cur, "POWER_LIMITED",
        power_diff > 1.0,
        "INFO", f"Power limited: Set={p_set_kw_in:.1f}kW, Actual={p_actual_kw_in:.1f}kW", power_diff, 1.0
    )

# =========================================================
#  COMMAND READ (CENTRALIZED CURSOR)
# =========================================================
def read_latest_command(cur) -> bool:
    """
    Reads newest unprocessed command from bess_commands (site level).
    Marks it processed when applied.
    """
    global p_set_kw, op_mode_id, last_processed_command_id

    sql = """
        SELECT command_id, p_set_kw, mode_set
        FROM bess_commands
        WHERE processed = FALSE
        ORDER BY ts DESC
        LIMIT 1;
    """
    cur.execute(sql)
    row = cur.fetchone()
    if not row:
        return False

    cmd_id, latest_p, mode_str = row
    if cmd_id <= last_processed_command_id:
        return False

    p_set_kw = float(latest_p)
    mode_str_u = (mode_str or "").upper()

    if mode_str_u == "DISCHARGE":
        op_mode_id = MODE_DISCHARGE
    elif mode_str_u == "CHARGE":
        op_mode_id = MODE_CHARGE
    elif mode_str_u == "IDLE":
        op_mode_id = MODE_IDLE
    else:
        op_mode_id = mode_from_setpoint(p_set_kw)

    log_event(
        cur, "COMMAND_RECEIVED",
        f"Command ID {cmd_id}: P_set={p_set_kw:.1f}kW, Mode={mode_str_u or 'AUTO'}",
        p_set_kw, None
    )

    cur.execute("UPDATE bess_commands SET processed = TRUE WHERE command_id = %s;", (cmd_id,))
    last_processed_command_id = cmd_id

    print(f"[{datetime.now().strftime('%H:%M:%S')}] COMMAND EXECUTED → ID {cmd_id}, P_set={p_set_kw:.1f} kW, Mode={mode_str_u or 'AUTO'}")
    return True

# =========================================================
#  SIMULATION STEP
# =========================================================
def simulate_fleet_step(site_p_set_kw: float):
    """
    Returns:
      inv_rows: list[(inverter_id, mode, p_set_kw, p_actual_kw, vdc, idc, temp_c, fault)]
      bat_rows: list[(battery_id, soc, vdc, idc, p_dc_kw, temp_c, fault)]
      site: (soc, mode, p_set_kw, p_actual_kw, vdc, idc, temp_c)

    The pure simulation model now lives in src/simulator/fleet.py.
    This wrapper preserves the old function contract for the runtime loop.
    """
    return fleet.step(site_p_set_kw)

# =========================================================
#  FAST INSERTS (execute_values)
# =========================================================
def insert_inverters(cur, inv_rows):
    execute_values(
        cur,
        """
        INSERT INTO inverter_status
        (ts, inverter_id, mode, p_set_kw, p_actual_kw, vdc, idc, temp_c, fault)
        VALUES %s
        """,
        inv_rows,
        template="(NOW(), %s, %s, %s, %s, %s, %s, %s, %s)"
    )

def insert_batteries(cur, bat_rows):
    execute_values(
        cur,
        """
        INSERT INTO battery_status
        (ts, battery_id, soc, vdc, idc, p_dc_kw, temp_c, fault)
        VALUES %s
        """,
        bat_rows,
        template="(NOW(), %s, %s, %s, %s, %s, %s, %s)"
    )

def insert_site(cur, site_tuple, active_alarm_count: int):
    soc, mode, p_set, p_actual, vdc, idc, temp_c = site_tuple
    cur.execute(
        """
        INSERT INTO site_status
        (ts, soc, mode, p_set_kw, p_actual_kw, vdc, idc, temp_c, active_alarms)
        VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (soc, mode, p_set, p_actual, vdc, idc, temp_c, active_alarm_count)
    )

# =========================================================
#  SITE SHORTFALL ALARM (DEBOUNCED)
# =========================================================
def update_site_shortfall_alarm(cur, p_set_site: float, p_actual_site: float):
    global site_shortfall_counter

    diff = abs(p_set_site - p_actual_site)
    if diff > ALARM_THRESHOLDS["site_shortfall_kw"]:
        site_shortfall_counter += 1
    else:
        site_shortfall_counter = 0

    condition = site_shortfall_counter >= ALARM_THRESHOLDS["site_shortfall_secs"]

    check_and_log_alarm(
        cur,
        "SITE_POWER_SHORTFALL",
        condition,
        "FAULT",
        f"Site cannot meet setpoint for {ALARM_THRESHOLDS['site_shortfall_secs']}s. "
        f"Set={p_set_site:.1f}kW Actual={p_actual_site:.1f}kW",
        diff,
        ALARM_THRESHOLDS["site_shortfall_kw"],
    )

# =========================================================
#  MAIN LOOP
# =========================================================
def main():
    global p_set_kw

    print("--- BESS Fleet Simulation Started ---")
    print(f"Inverters: {N_INVERTERS} | Batteries: {N_BATTERIES}")
    print(f"Initial SOC(avg): {fleet.average_soc:.2f}%")

    conn = get_connection()
    cur = conn.cursor()

    try:
        init_alarm_table(cur)
        load_active_alarms(cur)
        log_event(cur, "SYSTEM_START", "BESS fleet simulation started", r2(fleet.average_soc), None)
        if clear_alarm(cur, "SYSTEM_FAULT"):
            active_alarms.discard("SYSTEM_FAULT")
        conn.commit()

        while True:
            loop_start = time.time()

            # Read commands each second
            read_latest_command(cur)

            # Sim step
            inv_rows, bat_rows, site_tuple = simulate_fleet_step(p_set_kw)
            soc_site, mode_site, p_set_site, p_actual_site, vdc_site, idc_site, temp_site = site_tuple

            # Alarms
            check_all_alarms(cur, soc_site, temp_site, vdc_site, idc_site, p_set_site, p_actual_site)
            update_site_shortfall_alarm(cur, p_set_site, p_actual_site)

            # Inserts
            insert_inverters(cur, inv_rows)
            insert_batteries(cur, bat_rows)
            insert_site(cur, site_tuple, len(active_alarms))

            conn.commit()

            alarm_indicator = f" [{len(active_alarms)} ALARMS]" if active_alarms else ""
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] SITE → "
                f"SOC={soc_site:.2f}% | P_set={p_set_site:.1f} kW | "
                f"P_actual={p_actual_site:.1f} kW | Vdc={vdc_site:.1f} V | "
                f"I={idc_site:.1f} A | Temp={temp_site:.1f} °C | Mode={mode_site} ({map_mode_id_to_text(mode_site)})"
                f"{alarm_indicator}"
            )

            elapsed = time.time() - loop_start
            sleep_time = TELEMETRY_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Simulation stopped by user")
        try:
            log_event(cur, "SYSTEM_STOP", "BESS fleet simulation stopped by user", None, None)
            conn.commit()
        except Exception:
            pass

    except Exception as e:
        print(f"\n[FAULT] Simulation crashed: {e}")
        try:
            log_alarm(cur, "SYSTEM_FAULT", "FAULT", f"Simulation crashed: {str(e)}", None, None)
            conn.commit()
        except Exception:
            pass
        raise

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
