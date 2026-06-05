#!/usr/bin/env python3
"""
BESS OPC-UA <-> Postgres bridge (Fleet + Stable Under Load)

Creates OPC structure:
  BESS1/Site/*
  BESS1/Inverters/INV01..INV10/*
  BESS1/Batteries/BAT01..BAT20/*

Reads telemetry from Postgres tables:
  - site_status (latest)
  - inverter_status (latest row per inverter_id)
  - battery_status (latest row per battery_id)

Writes commands to:
  - bess_commands (when OPC Site/ApplyCommand is pulsed)

Stability + performance:
  - Only writes OPC nodes when value changes (deadband)
  - Command inserts survive DB restarts (reconnect + retry)
  - DB read reconnect if needed
  - Optional: bind endpoint to a specific IP instead of 0.0.0.0

Run:
  source venv/bin/activate
  python opc_bridge.py
"""

import time
import os
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from opcua import Server, ua

# =========================
#  DB CONFIG
# =========================
DB_CONFIG = {
    "host": os.getenv("BESS_DB_HOST", "DB_HOST"),
    "database": os.getenv("BESS_DB_NAME", "bess"),
    "user": os.getenv("BESS_DB_USER", "bessuser"),
    "password": os.getenv("BESS_DB_PASSWORD", "CHANGE_ME"),
    "port": int(os.getenv("BESS_DB_PORT", "5432")),
}

# =========================
#  FLEET SIZE
# =========================
N_INVERTERS = 10
N_BATTERIES = 20

# =========================
#  OPC CONFIG
# =========================
# For lab safety, you can bind to a specific interface, e.g.:
#   OPC_ENDPOINT = "opc.tcp://SOURCEw_IP:4840"
# Leaving it as 0.0.0.0 exposes to all networks on the VM.
OPC_ENDPOINT = os.getenv("BESS_OPC_ENDPOINT", "opc.tcp://OPC_HOST:4840")
OPC_SERVER_NAME = "BESS_OPC_SERVER"
OPC_NAMESPACE_URI = "http://bess.local"

# =========================
#  UPDATE RATE
# =========================
POLL_SECONDS = 1.0

# =========================
#  DEAD-BANDS (reduce load)
# =========================
DB_FLOAT_DEADBAND = 0.001  # ignore tiny float changes
SOC_DEADBAND = 0.01
P_DEADBAND = 0.1
V_DEADBAND = 0.1
I_DEADBAND = 0.1
T_DEADBAND = 0.05
COMMAND_DEADBAND_KW = 0.1
SITE_MAX_COMMAND_KW = 250.0

# =========================
#  DATABASE HELPERS
# =========================
def connect_db():
    """Connect to Postgres, retry until success."""
    while True:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.autocommit = True
            print("[DB] Connected to Postgres")
            return conn
        except Exception as e:
            print(f"[DB] Connection failed: {e}")
            time.sleep(5)


def read_latest_site_status(conn):
    """Read latest row from site_status."""
    sql = """
        SELECT
            soc,
            mode,
            p_set_kw,
            p_actual_kw,
            vdc,
            idc,
            temp_c,
            active_alarms,
            ts
        FROM site_status
        ORDER BY ts DESC
        LIMIT 1;
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql)
        return cur.fetchone()


def read_latest_inverter_status(conn):
    """Read latest row per inverter_id from inverter_status."""
    sql = """
        SELECT DISTINCT ON (inverter_id)
            inverter_id,
            mode,
            p_set_kw,
            p_actual_kw,
            vdc,
            idc,
            temp_c,
            fault,
            ts
        FROM inverter_status
        ORDER BY inverter_id, ts DESC;
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql)
        return cur.fetchall()


def read_latest_battery_status(conn):
    """Read latest row per battery_id from battery_status."""
    sql = """
        SELECT DISTINCT ON (battery_id)
            battery_id,
            soc,
            vdc,
            idc,
            p_dc_kw,
            temp_c,
            fault,
            ts
        FROM battery_status
        ORDER BY battery_id, ts DESC;
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql)
        return cur.fetchall()


def insert_command_safe(conn, p_set_kw, mode_text, source_ip=None):
    """
    Insert command into bess_commands.
    If DB restarts, reconnect and retry once.
    Returns (conn, success_bool).
    """
    if source_ip is None:
        source_ip = os.getenv("BESS_OPC_SOURCE_IP", "SOURCE_IP")

    sql = """
        INSERT INTO bess_commands (p_set_kw, mode_set, source_ip)
        VALUES (%s, %s, %s);
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (p_set_kw, mode_text, source_ip))
        print(f"[CMD] Inserted command: P_set={p_set_kw:.1f} kW, Mode={mode_text}")
        return conn, True
    except Exception as e:
        print(f"[CMD] Insert failed ({e}) -> reconnecting and retrying once")
        try:
            conn.close()
        except Exception:
            pass
        conn = connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (p_set_kw, mode_text, source_ip))
            print(f"[CMD] Inserted command after reconnect: P_set={p_set_kw:.1f} kW, Mode={mode_text}")
            return conn, True
        except Exception as e2:
            print(f"[CMD] Retry failed: {e2}")
            return conn, False


# =========================
#  MODE MAPPING HELPERS
# =========================
def map_mode_id_to_text(mode_id: int) -> str:
    if mode_id == 1:
        return "IDLE"
    elif mode_id == 2:
        return "CHARGE"
    elif mode_id == 3:
        return "DISCHARGE"
    return "UNKNOWN"


def map_p_set_to_mode_text(p_set_kw: float) -> str:
    if p_set_kw > 1.0:
        return "CHARGE"
    elif p_set_kw < -1.0:
        return "DISCHARGE"
    else:
        return "IDLE"


def build_command(mode_id: int, p_set_kw: float):
    """
    Build an operator command from staged OPC inputs.

    The HMI setpoint is an unsigned magnitude. Mode determines direction.
    IDLE always commands 0 kW, even if the staged magnitude is non-zero.
    """
    mode_text = map_mode_id_to_text(mode_id)
    if mode_text == "UNKNOWN":
        return None, None, f"unsupported mode {mode_id}"

    p_mag_kw = abs(float(p_set_kw))
    if p_mag_kw > SITE_MAX_COMMAND_KW:
        return None, None, f"setpoint {p_mag_kw:.1f} kW exceeds {SITE_MAX_COMMAND_KW:.1f} kW limit"

    if mode_text == "IDLE":
        return 0.0, mode_text, None

    if p_mag_kw <= COMMAND_DEADBAND_KW:
        return None, None, f"{mode_text} requires setpoint above {COMMAND_DEADBAND_KW:.1f} kW"

    return p_mag_kw, mode_text, None


# =========================
#  OPC HELPERS
# =========================
_LAST = {}

def write_node_value(node, value, vtype=None):
    if vtype is not None:
        dv = ua.DataValue(ua.Variant(value, vtype))
        node.set_value(dv)
    else:
        node.set_value(value)


def set_if_changed(node, value, key, deadband=0.0, vtype=None):
    """
    Only update OPC node if it changed (or changed beyond deadband).
    This dramatically reduces load when you have many nodes.
    """
    prev = _LAST.get(key)

    # deadband for numeric values
    if prev is not None and isinstance(value, (int, float)) and isinstance(prev, (int, float)):
        try:
            if abs(float(value) - float(prev)) <= float(deadband):
                return
        except Exception:
            pass

    # exact compare for non-numeric
    if prev == value:
        return

    _LAST[key] = value
    write_node_value(node, value, vtype)


def force_set_node(node, value, key, vtype=None):
    """Write an OPC node even when the change cache already has that value."""
    _LAST[key] = value
    write_node_value(node, value, vtype)


def make_inv_name(i: int) -> str:
    return f"INV{i:02d}"


def make_bat_name(i: int) -> str:
    return f"BAT{i:02d}"


# =========================
#  MAIN
# =========================
def main():
    # ========= OPC UA SERVER SETUP =========
    server = Server()
    server.set_endpoint(OPC_ENDPOINT)
    server.set_server_name(OPC_SERVER_NAME)

    idx = server.register_namespace(OPC_NAMESPACE_URI)

    objects = server.get_objects_node()
    bess = objects.add_object(idx, "BESS1")

    # Organize nodes
    site_obj = bess.add_object(idx, "Site")
    inv_root = bess.add_object(idx, "Inverters")
    bat_root = bess.add_object(idx, "Batteries")

    # --- Site tags ---
    site_soc_node        = site_obj.add_variable(idx, "SOC",          50.0)
    site_vdc_node        = site_obj.add_variable(idx, "Vdc",          800.0)
    site_idc_node        = site_obj.add_variable(idx, "Idc",          0.0)
    site_p_set_node      = site_obj.add_variable(idx, "P_set_kW",     0.0)
    site_p_actual_node   = site_obj.add_variable(idx, "P_actual_kW",  0.0)
    site_temp_node       = site_obj.add_variable(idx, "Temp_C",       25.0)
    site_mode_node       = site_obj.add_variable(idx, "Mode",         1)
    site_actual_mode_node = site_obj.add_variable(idx, "ActualMode",  1)
    site_apply_node      = site_obj.add_variable(idx, "ApplyCommand", False)
    site_alarms_node     = site_obj.add_variable(idx, "ActiveAlarms", 0)

    # Writable command nodes
    site_p_set_node.set_writable()
    site_mode_node.set_writable()
    site_apply_node.set_writable()

    # --- Inverters ---
    inv_nodes = {}  # inverter_id -> dict of nodes
    for inv_id in range(1, N_INVERTERS + 1):
        inv_name = make_inv_name(inv_id)
        inv_obj = inv_root.add_object(idx, inv_name)

        inv_nodes[inv_id] = {
            "Mode":        inv_obj.add_variable(idx, "Mode",        1),
            "P_set_kW":    inv_obj.add_variable(idx, "P_set_kW",    0.0),
            "P_actual_kW": inv_obj.add_variable(idx, "P_actual_kW", 0.0),
            "Vdc":         inv_obj.add_variable(idx, "Vdc",         800.0),
            "Idc":         inv_obj.add_variable(idx, "Idc",         0.0),
            "Temp_C":      inv_obj.add_variable(idx, "Temp_C",      25.0),
            "Fault":       inv_obj.add_variable(idx, "Fault",       False),
        }

    # --- Batteries ---
    bat_nodes = {}  # battery_id -> dict of nodes
    for bat_id in range(1, N_BATTERIES + 1):
        bat_name = make_bat_name(bat_id)
        bat_obj = bat_root.add_object(idx, bat_name)

        bat_nodes[bat_id] = {
            "SOC":     bat_obj.add_variable(idx, "SOC",     50.0),
            "Vdc":     bat_obj.add_variable(idx, "Vdc",     800.0),
            "Idc":     bat_obj.add_variable(idx, "Idc",     0.0),
            "P_dc_kW": bat_obj.add_variable(idx, "P_dc_kW", 0.0),
            "Temp_C":  bat_obj.add_variable(idx, "Temp_C",  25.0),
            "Fault":   bat_obj.add_variable(idx, "Fault",   False),
        }

    print(f"[OPC] Starting OPC UA server at {OPC_ENDPOINT} …")
    server.start()
    print("[OPC] Server started.")

    # DB connection
    conn = connect_db()

    # Command apply tracking. Mode/P_set are staged until ApplyCommand is pulsed.
    last_apply_value = False
    command_nodes_initialized = False

    try:
        while True:
            # ===== 1) READ TELEMETRY FROM DB =====
            try:
                site = read_latest_site_status(conn)
                invs = read_latest_inverter_status(conn)
                bats = read_latest_battery_status(conn)
            except Exception as e:
                print(f"[DB] Read error: {e} (reconnecting)")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = connect_db()
                site, invs, bats = None, [], []

            # ===== 2) PUSH TELEMETRY TO OPC (ONLY IF CHANGED) =====
            if site:
                soc      = float(site.get("soc") or 0.0)
                mode     = int(site.get("mode") or 0)
                p_set_db = float(site.get("p_set_kw") or 0.0)
                p_actual = float(site.get("p_actual_kw") or 0.0)
                vdc      = float(site.get("vdc") or 0.0)
                idc      = float(site.get("idc") or 0.0)
                temp_c   = float(site.get("temp_c") or 25.0)
                alarms   = int(site.get("active_alarms") or 0)
                ts       = site.get("ts") or datetime.utcnow()

                set_if_changed(site_soc_node, soc, "site/soc", deadband=SOC_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(site_vdc_node, vdc, "site/vdc", deadband=V_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(site_idc_node, idc, "site/idc", deadband=I_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(site_p_actual_node, p_actual, "site/p_actual", deadband=P_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(site_temp_node, temp_c, "site/temp", deadband=T_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(site_actual_mode_node, mode, "site/actual_mode", deadband=0.0, vtype=ua.VariantType.Int16)
                set_if_changed(site_alarms_node, alarms, "site/alarms", deadband=0.0, vtype=ua.VariantType.Int32)

                if not command_nodes_initialized:
                    set_if_changed(site_mode_node, mode, "site/cmd_mode", deadband=0.0, vtype=ua.VariantType.Int16)
                    set_if_changed(site_p_set_node, abs(p_set_db), "site/cmd_p_set", deadband=P_DEADBAND, vtype=ua.VariantType.Float)
                    command_nodes_initialized = True

                # NOTE: Site/Mode and Site/P_set_kW are staged command inputs.
                # Live telemetry mode is exposed as Site/ActualMode.

                print(
                    f"[SITE] {ts} SOC={soc:.2f}% P_set(DB)={p_set_db:.1f}kW P_act={p_actual:.1f}kW "
                    f"Vdc={vdc:.1f}V Idc={idc:.1f}A Temp={temp_c:.2f}C Mode={mode} Alarms={alarms}"
                )

            # Inverters
            for row in invs or []:
                inv_id = int(row.get("inverter_id") or 0)
                nodes = inv_nodes.get(inv_id)
                if not nodes:
                    continue

                mode = int(row.get("mode") or 0)
                p_set = float(row.get("p_set_kw") or 0.0)
                p_act = float(row.get("p_actual_kw") or 0.0)
                vdc = float(row.get("vdc") or 0.0)
                idc = float(row.get("idc") or 0.0)
                temp = float(row.get("temp_c") or 0.0)
                fault = bool(row.get("fault") or False)

                set_if_changed(nodes["Mode"], mode, f"inv/{inv_id}/mode", deadband=0.0, vtype=ua.VariantType.Int16)
                set_if_changed(nodes["P_set_kW"], p_set, f"inv/{inv_id}/p_set", deadband=P_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["P_actual_kW"], p_act, f"inv/{inv_id}/p_act", deadband=P_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Vdc"], vdc, f"inv/{inv_id}/vdc", deadband=V_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Idc"], idc, f"inv/{inv_id}/idc", deadband=I_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Temp_C"], temp, f"inv/{inv_id}/temp", deadband=T_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Fault"], fault, f"inv/{inv_id}/fault", deadband=0.0, vtype=ua.VariantType.Boolean)

            # Batteries
            for row in bats or []:
                bat_id = int(row.get("battery_id") or 0)
                nodes = bat_nodes.get(bat_id)
                if not nodes:
                    continue

                soc = float(row.get("soc") or 0.0)
                vdc = float(row.get("vdc") or 0.0)
                idc = float(row.get("idc") or 0.0)
                pdc = float(row.get("p_dc_kw") or 0.0)
                temp = float(row.get("temp_c") or 0.0)
                fault = bool(row.get("fault") or False)

                set_if_changed(nodes["SOC"], soc, f"bat/{bat_id}/soc", deadband=SOC_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Vdc"], vdc, f"bat/{bat_id}/vdc", deadband=V_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Idc"], idc, f"bat/{bat_id}/idc", deadband=I_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["P_dc_kW"], pdc, f"bat/{bat_id}/pdc", deadband=P_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Temp_C"], temp, f"bat/{bat_id}/temp", deadband=T_DEADBAND, vtype=ua.VariantType.Float)
                set_if_changed(nodes["Fault"], fault, f"bat/{bat_id}/fault", deadband=0.0, vtype=ua.VariantType.Boolean)

            # ===== 3) WATCH OPC APPLY AND WRITE ONE COHERENT COMMAND TO DB =====
            try:
                cmd_p_set = float(site_p_set_node.get_value())
                cmd_mode = int(site_mode_node.get_value())
                apply_value = bool(site_apply_node.get_value())
            except Exception:
                cmd_p_set, cmd_mode, apply_value = None, None, False

            if cmd_p_set is not None and cmd_mode is not None and apply_value and not last_apply_value:
                command_p_set, mode_text, error = build_command(cmd_mode, cmd_p_set)
                if error:
                    print(f"[CMD] Rejected staged command: P_set={cmd_p_set:.1f} kW, Mode={cmd_mode} ({error})")
                    force_set_node(site_apply_node, False, "site/apply", vtype=ua.VariantType.Boolean)
                    apply_value = False
                else:
                    conn, ok = insert_command_safe(conn, command_p_set, mode_text)
                    if ok:
                        force_set_node(site_apply_node, False, "site/apply", vtype=ua.VariantType.Boolean)
                        apply_value = False

            last_apply_value = apply_value

            time.sleep(POLL_SECONDS)

    finally:
        try:
            conn.close()
        except Exception:
            pass
        server.stop()
        print("[OPC] Server stopped.")


if __name__ == "__main__":
    main()
