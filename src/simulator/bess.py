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
from datetime import datetime
from typing import Tuple

import psycopg2
from psycopg2.extras import execute_values

# =========================================================
#  DB CONFIG
# =========================================================
DB_CONFIG = {
    "host": "DB_HOST",
    "database": "bess",
    "user": "bessuser",
    "password": "CHANGE_ME",
    "port": 5432,
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

def clear_alarm(cur, alarm_code):
    sql = """
        UPDATE bess_alarms
        SET cleared = TRUE, cleared_ts = NOW()
        WHERE alarm_code = %s AND cleared = FALSE;
    """
    cur.execute(sql, (alarm_code,))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ ALARM CLEARED → {alarm_code}")

def check_and_log_alarm(cur, alarm_code, condition, severity_name, message, value=None, threshold=None):
    if condition:
        if alarm_code not in active_alarms:
            log_alarm(cur, alarm_code, severity_name, message, value, threshold)
            active_alarms.add(alarm_code)
        return True
    else:
        if alarm_code in active_alarms:
            clear_alarm(cur, alarm_code)
            active_alarms.remove(alarm_code)
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

    log_alarm(
        cur, "COMMAND_RECEIVED", "INFO",
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
    """
    site_p_set_limited = clamp(site_p_set_kw, SITE_MAX_DISCHARGE_KW, SITE_MAX_CHARGE_KW)

    # split across inverters (commanded)
    per_inv_set = site_p_set_limited / N_INVERTERS if N_INVERTERS else 0.0
    per_inv_set = clamp(per_inv_set, -INV_MAX_KW, INV_MAX_KW)

    dt_hours = TELEMETRY_INTERVAL / 3600.0
    per_bat_capacity_kwh = SITE_CAPACITY_KWH / N_BATTERIES

    inv_rows = []
    bat_rows = []

    # this is computed during the inverter loop
    p_actual_site = 0.0
    vdc_site_list = []
    temp_site_list = []

    for inv_idx in range(N_INVERTERS):
        inv_id = inv_idx + 1
        inv_set_kw = 0.0 if inverter_fault[inv_idx] else per_inv_set

        b1, b2 = inv_to_bats(inv_idx)
        per_bat_dc_kw = clamp(inv_set_kw / 2.0, -BAT_MAX_KW, BAT_MAX_KW)

        bat_v = []
        bat_i = []
        bat_t = []
        bat_fault_any = False

        for bat_idx in (b1, b2):
            bat_id = bat_idx + 1
            fault = battery_fault[bat_idx]

            if fault:
                bat_fault_any = True
                p_dc_kw = 0.0
            else:
                p_dc_kw = per_bat_dc_kw

            # SOC update
            if p_dc_kw >= 0:
                energy_change_kwh = p_dc_kw * dt_hours * BAT_ROUNDTRIP_EFF
            else:
                energy_change_kwh = p_dc_kw * dt_hours / BAT_ROUNDTRIP_EFF

            soc_new = battery_soc[bat_idx] + (energy_change_kwh / per_bat_capacity_kwh) * 100.0
            soc_new = clamp(soc_new, 0.0, 100.0)
            battery_soc[bat_idx] = soc_new

            # Vdc from SOC curve + noise
            vdc = 760.0 + (840.0 - 760.0) * (soc_new / 100.0) + random.uniform(-2.0, 2.0)
            idc = 0.0 if abs(vdc) < 1e-6 else (p_dc_kw * 1000.0 / vdc)
            temp_c = 25.0 + (abs(p_dc_kw) / 250.0) * 5.0 + random.uniform(-0.5, 0.5)

            bat_rows.append((
                bat_id,
                r2(soc_new),
                r2(vdc),
                r2(idc),
                r2(p_dc_kw),
                r2(temp_c),
                bool(fault),
            ))

            bat_v.append(vdc)
            bat_i.append(idc)
            bat_t.append(temp_c)

        vdc_inv = sum(bat_v) / 2.0
        idc_inv = sum(bat_i)
        p_dc_inv = per_bat_dc_kw * 2.0

        # DC->AC inverter efficiency
        if p_dc_inv >= 0:
            p_ac_inv = p_dc_inv * INV_EFF
        else:
            p_ac_inv = p_dc_inv / INV_EFF

        # Determine inverter mode/fault
        if inverter_fault[inv_idx] or bat_fault_any:
            mode_inv = MODE_IDLE
            fault_inv = True
            p_ac_inv = 0.0
        else:
            mode_inv = mode_from_setpoint(p_ac_inv)  # mode follows ACTUAL power
            fault_inv = False

        temp_inv = sum(bat_t) / 2.0

        inv_rows.append((
            inv_id,
            int(mode_inv),
            r2(inv_set_kw),
            r2(p_ac_inv),
            r2(vdc_inv),
            r2(idc_inv),
            r2(temp_inv),
            bool(fault_inv),
        ))

        p_actual_site += p_ac_inv
        vdc_site_list.append(vdc_inv)
        temp_site_list.append(temp_inv)

    # Site aggregations
    soc_site = sum(battery_soc) / N_BATTERIES
    vdc_site = sum(vdc_site_list) / len(vdc_site_list) if vdc_site_list else 800.0
    temp_site = sum(temp_site_list) / len(temp_site_list) if temp_site_list else 25.0
    idc_site = 0.0 if abs(vdc_site) < 1e-6 else (p_actual_site * 1000.0 / vdc_site)

    # ✅ FIX: Site Mode must reflect ACTUAL net AC power (realistic)
    mode_site = mode_from_setpoint(p_actual_site)

    site_tuple = (
        r2(soc_site),
        int(mode_site),
        r2(site_p_set_kw),      # keep ORIGINAL setpoint for logging/alarms
        r2(p_actual_site),
        r2(vdc_site),
        r2(idc_site),
        r2(temp_site),
    )

    return inv_rows, bat_rows, site_tuple

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
    print(f"Initial SOC(avg): {sum(battery_soc)/N_BATTERIES:.2f}%")

    conn = get_connection()
    cur = conn.cursor()

    try:
        init_alarm_table(cur)
        log_alarm(cur, "SYSTEM_START", "INFO", "BESS fleet simulation started", r2(sum(battery_soc)/N_BATTERIES), None)
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
            log_alarm(cur, "SYSTEM_STOP", "INFO", "BESS fleet simulation stopped by user", None, None)
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
