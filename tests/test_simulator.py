from src.simulator.bess import (
    SEVERITY,
    active_alarms,
    check_and_log_alarm,
    clear_alarm,
    log_event,
)


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
