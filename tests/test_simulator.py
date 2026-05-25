from src.simulator.bess import (
    SEVERITY,
    active_alarms,
    check_and_log_alarm,
    clear_alarm,
    log_event,
)
from src.simulator.fleet import BESSFleet


class FakeCursor:
    def __init__(self, rowcount=0):
        self.executed = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return (123,)


def test_log_event_records_info_as_cleared():
    cur = FakeCursor()

    event_id = log_event(cur, "COMMAND_RECEIVED", "Command accepted", 10.0, None)

    assert event_id == 123
    sql, params = cur.executed[0]
    assert "cleared, cleared_ts" in sql
    assert "TRUE, NOW()" in sql
    assert params == ("COMMAND_RECEIVED", SEVERITY["INFO"], "Command accepted", 10.0, None)


def test_false_alarm_condition_clears_stale_db_alarm():
    cur = FakeCursor(rowcount=1)
    active_alarms.clear()

    result = check_and_log_alarm(
        cur,
        "SOC_CRITICAL_HIGH",
        False,
        "CRITICAL",
        "Site SOC critically high",
        80.0,
        95.0,
    )

    assert result is False
    sql, params = cur.executed[0]
    assert "UPDATE bess_alarms" in sql
    assert params == ("SOC_CRITICAL_HIGH",)
    assert "SOC_CRITICAL_HIGH" not in active_alarms


def test_clear_alarm_returns_number_of_rows_cleared():
    cur = FakeCursor(rowcount=2)

    cleared_count = clear_alarm(cur, "SYSTEM_FAULT")

    assert cleared_count == 2
    sql, params = cur.executed[0]
    assert "SET cleared = TRUE" in sql
    assert params == ("SYSTEM_FAULT",)


def test_fleet_dispatch_is_non_uniform_but_tracks_setpoint():
    fleet = BESSFleet(n_inverters=10, n_batteries=20)

    inv_rows, bat_rows, site = fleet.step(100.0)

    inv_setpoints = [row[2] for row in inv_rows]
    battery_powers = [row[4] for row in bat_rows]

    assert len(set(inv_setpoints)) > 1
    assert len(set(battery_powers)) > 1
    assert abs(sum(inv_setpoints) - 100.0) <= 0.2
    assert abs(site[3] - sum(row[3] for row in inv_rows)) <= 0.2


def test_faulted_inverter_is_excluded_from_dispatch():
    fleet = BESSFleet(n_inverters=10, n_batteries=20)
    fleet.inverters[0].fault = True

    inv_rows, _bat_rows, _site = fleet.step(100.0)

    assert inv_rows[0][2] == 0.0
    assert inv_rows[0][3] == 0.0
    assert abs(sum(row[2] for row in inv_rows) - 100.0) <= 0.2


def test_faulted_battery_excludes_parent_inverter_from_dispatch():
    fleet = BESSFleet(n_inverters=10, n_batteries=20)
    fleet.batteries[0].fault = True

    inv_rows, bat_rows, _site = fleet.step(100.0)

    assert inv_rows[0][2] == 0.0
    assert inv_rows[0][3] == 0.0
    assert bat_rows[0][4] == 0.0
    assert bat_rows[1][4] == 0.0
    assert abs(sum(row[2] for row in inv_rows) - 100.0) <= 0.2


def test_battery_soc_headroom_changes_pair_split():
    fleet = BESSFleet(n_inverters=10, n_batteries=20)
    fleet.batteries[0].soc = 94.9
    fleet.batteries[1].soc = 50.0

    _inv_rows, bat_rows, _site = fleet.step(40.0)

    bat1 = next(row for row in bat_rows if row[0] == 1)
    bat2 = next(row for row in bat_rows if row[0] == 2)

    assert bat1[4] < bat2[4]
