from src.simulator import bess


class FakeCursor:
    def __init__(self, rowcount=0):
        self.executed = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return (123,)


class FakeInjectionCursor(FakeCursor):
    def __init__(self, row):
        super().__init__()
        self.row = row

    def fetchall(self):
        return []

    def fetchone(self):
        return self.row


def reset_alarm_state():
    bess.active_alarms.clear()
    bess.site_shortfall_counter = 0


def alarm_inserts(cur):
    return [params for sql, params in cur.executed if "INSERT INTO bess_alarms" in sql]


def alarm_clears(cur):
    return [params[0] for sql, params in cur.executed if "UPDATE bess_alarms" in sql]


def inv_row(inverter_id=1, temp_c=25.0, fault=False):
    return (inverter_id, bess.MODE_IDLE, 0.0, 0.0, 800.0, 0.0, temp_c, fault)


def bat_row(battery_id=1, soc=50.0, temp_c=25.0, fault=False):
    return (battery_id, soc, 800.0, 0.0, 0.0, temp_c, fault)


def test_equipment_alarm_code_format_uses_zero_padded_source_id():
    assert bess.format_equipment_code("INV", 3, "TEMP_HIGH") == "INV03_TEMP_HIGH"
    assert bess.format_equipment_code("BAT", 12, "TEMP_CRITICAL") == "BAT12_TEMP_CRITICAL"


def test_equipment_injection_target_parser_accepts_common_target_formats():
    assert bess.parse_equipment_target_id("INV03", "INV", 1, 10) == 3
    assert bess.parse_equipment_target_id("inv-3", "INV", 1, 10) == 3
    assert bess.parse_equipment_target_id("INV_03", "INV", 1, 10) == 3
    assert bess.parse_equipment_target_id("3", "INV", 1, 10) == 3
    assert bess.parse_equipment_target_id("INV11", "INV", 1, 10) is None
    assert bess.parse_equipment_target_id("BAT00", "BAT", 1, 20) is None
    assert bess.parse_equipment_target_id("site", "INV", 1, 10) is None


def test_read_active_alarm_test_injection_includes_target():
    cur = FakeInjectionCursor((42, "FORCE_INV_TEMP", "INV03", 50.0, "2026-07-03 18:00:00+10", "test"))

    injection = bess.read_active_alarm_test_injection(cur)

    assert injection["injection_id"] == 42
    assert injection["scenario"] == "FORCE_INV_TEMP"
    assert injection["target"] == "INV03"
    assert injection["value"] == 50.0


def test_inverter_temperature_high_and_critical_hysteresis_can_coexist():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=3, temp_c=39.9)])
    assert "INV03_TEMP_HIGH" not in bess.active_alarms

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=3, temp_c=40.0)])
    assert "INV03_TEMP_HIGH" in bess.active_alarms

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=3, temp_c=50.0)])
    assert "INV03_TEMP_HIGH" in bess.active_alarms
    assert "INV03_TEMP_CRITICAL" in bess.active_alarms

    inserts = alarm_inserts(cur)
    assert any(params[0] == "INV03_TEMP_HIGH" and params[1] == bess.SEVERITY["WARNING"] for params in inserts)
    assert any(params[0] == "INV03_TEMP_CRITICAL" and params[1] == bess.SEVERITY["CRITICAL"] for params in inserts)

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=3, temp_c=46.0)])
    assert "INV03_TEMP_CRITICAL" in bess.active_alarms

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=3, temp_c=45.0)])
    assert "INV03_TEMP_CRITICAL" not in bess.active_alarms
    assert "INV03_TEMP_HIGH" in bess.active_alarms

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=3, temp_c=37.0)])
    assert "INV03_TEMP_HIGH" not in bess.active_alarms
    assert "INV03_TEMP_CRITICAL" in alarm_clears(cur)
    assert "INV03_TEMP_HIGH" in alarm_clears(cur)


def test_battery_temperature_high_and_critical_hysteresis_can_coexist():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    bess.check_battery_alarms(cur, [bat_row(battery_id=12, temp_c=34.9)])
    assert "BAT12_TEMP_HIGH" not in bess.active_alarms

    bess.check_battery_alarms(cur, [bat_row(battery_id=12, temp_c=35.0)])
    assert "BAT12_TEMP_HIGH" in bess.active_alarms

    bess.check_battery_alarms(cur, [bat_row(battery_id=12, temp_c=45.0)])
    assert "BAT12_TEMP_HIGH" in bess.active_alarms
    assert "BAT12_TEMP_CRITICAL" in bess.active_alarms

    bess.check_battery_alarms(cur, [bat_row(battery_id=12, temp_c=42.0)])
    assert "BAT12_TEMP_CRITICAL" not in bess.active_alarms
    assert "BAT12_TEMP_HIGH" in bess.active_alarms

    bess.check_battery_alarms(cur, [bat_row(battery_id=12, temp_c=33.0)])
    assert "BAT12_TEMP_HIGH" not in bess.active_alarms


def test_inverter_and_battery_unavailable_raise_and_clear():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=4, fault=True)])
    bess.check_battery_alarms(cur, [bat_row(battery_id=7, fault=True)])

    assert "INV04_UNAVAILABLE" in bess.active_alarms
    assert "BAT07_UNAVAILABLE" in bess.active_alarms

    bess.check_inverter_alarms(cur, [inv_row(inverter_id=4, fault=False)])
    bess.check_battery_alarms(cur, [bat_row(battery_id=7, fault=False)])

    assert "INV04_UNAVAILABLE" not in bess.active_alarms
    assert "BAT07_UNAVAILABLE" not in bess.active_alarms
    assert "INV04_UNAVAILABLE" in alarm_clears(cur)
    assert "BAT07_UNAVAILABLE" in alarm_clears(cur)


def test_battery_soc_imbalance_raises_and_clears_with_hysteresis():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    balanced_rows = [
        bat_row(battery_id=1, soc=50.0),
        bat_row(battery_id=2, soc=57.9),
    ]
    bess.check_battery_soc_imbalance_alarm(cur, balanced_rows)
    assert "BATTERY_SOC_IMBALANCE" not in bess.active_alarms

    imbalanced_rows = [
        bat_row(battery_id=1, soc=50.0),
        bat_row(battery_id=2, soc=58.0),
    ]
    bess.check_battery_soc_imbalance_alarm(cur, imbalanced_rows)
    assert "BATTERY_SOC_IMBALANCE" in bess.active_alarms

    still_imbalanced_rows = [
        bat_row(battery_id=1, soc=50.0),
        bat_row(battery_id=2, soc=55.1),
    ]
    bess.check_battery_soc_imbalance_alarm(cur, still_imbalanced_rows)
    assert "BATTERY_SOC_IMBALANCE" in bess.active_alarms

    cleared_rows = [
        bat_row(battery_id=1, soc=50.0),
        bat_row(battery_id=2, soc=55.0),
    ]
    bess.check_battery_soc_imbalance_alarm(cur, cleared_rows)
    assert "BATTERY_SOC_IMBALANCE" not in bess.active_alarms
    assert "BATTERY_SOC_IMBALANCE" in alarm_clears(cur)


def test_stage2_combined_checker_runs_all_equipment_alarm_groups():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    bess.check_stage2_equipment_alarms(
        cur,
        [inv_row(inverter_id=2, temp_c=40.0)],
        [
            bat_row(battery_id=1, soc=50.0, temp_c=35.0),
            bat_row(battery_id=2, soc=58.0, temp_c=25.0),
        ],
    )

    assert "INV02_TEMP_HIGH" in bess.active_alarms
    assert "BAT01_TEMP_HIGH" in bess.active_alarms
    assert "BATTERY_SOC_IMBALANCE" in bess.active_alarms


def test_force_inverter_temperature_injection_drives_stage2_alarm():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)
    injection = {
        "scenario": "FORCE_INV_TEMP",
        "target": "INV03",
        "value": 50.0,
    }

    inv_rows, bat_rows = bess.apply_equipment_alarm_test_injection(
        injection,
        [inv_row(inverter_id=3, temp_c=25.0)],
        [bat_row(battery_id=1)],
    )

    assert inv_rows[0][6] == 50.0
    bess.check_stage2_equipment_alarms(cur, inv_rows, bat_rows)
    assert "INV03_TEMP_HIGH" in bess.active_alarms
    assert "INV03_TEMP_CRITICAL" in bess.active_alarms


def test_force_battery_temperature_injection_drives_stage2_alarm():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)
    injection = {
        "scenario": "FORCE_BAT_TEMP",
        "target": "BAT12",
        "value": 45.0,
    }

    inv_rows, bat_rows = bess.apply_equipment_alarm_test_injection(
        injection,
        [inv_row(inverter_id=1)],
        [bat_row(battery_id=12, temp_c=25.0)],
    )

    assert bat_rows[0][5] == 45.0
    bess.check_stage2_equipment_alarms(cur, inv_rows, bat_rows)
    assert "BAT12_TEMP_HIGH" in bess.active_alarms
    assert "BAT12_TEMP_CRITICAL" in bess.active_alarms


def test_force_equipment_fault_injections_drive_unavailable_alarms():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    inv_rows, bat_rows = bess.apply_equipment_alarm_test_injection(
        {"scenario": "FORCE_INV_FAULT", "target": "INV04", "value": 1.0},
        [inv_row(inverter_id=4, fault=False)],
        [bat_row(battery_id=7, fault=False)],
    )
    inv_rows, bat_rows = bess.apply_equipment_alarm_test_injection(
        {"scenario": "FORCE_BAT_FAULT", "target": "BAT07", "value": 1.0},
        inv_rows,
        bat_rows,
    )

    assert inv_rows[0][7] is True
    assert bat_rows[0][6] is True
    bess.check_stage2_equipment_alarms(cur, inv_rows, bat_rows)
    assert "INV04_UNAVAILABLE" in bess.active_alarms
    assert "BAT07_UNAVAILABLE" in bess.active_alarms


def test_force_battery_soc_injection_drives_soc_imbalance_alarm():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)
    injection = {
        "scenario": "FORCE_BAT_SOC",
        "target": "BAT02",
        "value": 70.0,
    }

    inv_rows, bat_rows = bess.apply_equipment_alarm_test_injection(
        injection,
        [inv_row(inverter_id=1)],
        [
            bat_row(battery_id=1, soc=50.0),
            bat_row(battery_id=2, soc=51.0),
        ],
    )

    assert bat_rows[1][1] == 70.0
    bess.check_stage2_equipment_alarms(cur, inv_rows, bat_rows)
    assert "BATTERY_SOC_IMBALANCE" in bess.active_alarms


def test_equipment_injection_ignores_invalid_target_without_changing_rows():
    inv_rows = [inv_row(inverter_id=1, temp_c=25.0)]
    bat_rows = [bat_row(battery_id=1, temp_c=25.0)]

    new_inv_rows, new_bat_rows = bess.apply_equipment_alarm_test_injection(
        {"scenario": "FORCE_INV_TEMP", "target": "INV99", "value": 50.0},
        inv_rows,
        bat_rows,
    )

    assert new_inv_rows == inv_rows
    assert new_bat_rows == bat_rows
