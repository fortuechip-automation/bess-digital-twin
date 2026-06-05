from src.simulator import bess


class FakeCursor:
    def __init__(self, rowcount=0):
        self.executed = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return (123,)


def reset_alarm_state():
    bess.active_alarms.clear()
    bess.site_shortfall_counter = 0


def alarm_inserts(cur):
    return [params for sql, params in cur.executed if "INSERT INTO bess_alarms" in sql]


def alarm_clears(cur):
    return [params[0] for sql, params in cur.executed if "UPDATE bess_alarms" in sql]


def run_site_check(cur, *, soc=50.0, temp_c=25.0, vdc=800.0, idc=0.0, p_set=0.0, p_actual=0.0):
    bess.check_all_alarms(cur, soc, temp_c, vdc, idc, p_set, p_actual)


def assert_active(*alarm_codes):
    assert bess.active_alarms == set(alarm_codes)


def test_normal_state_produces_no_active_alarms():
    reset_alarm_state()
    cur = FakeCursor()

    run_site_check(cur)
    bess.update_site_shortfall_alarm(cur, 0.0, 0.0)

    assert_active()


def test_soc_high_raises_and_clears_with_hysteresis():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    run_site_check(cur, soc=89.9)
    assert "SOC_HIGH" not in bess.active_alarms

    run_site_check(cur, soc=90.0)
    assert "SOC_HIGH" in bess.active_alarms

    run_site_check(cur, soc=89.0)
    assert "SOC_HIGH" in bess.active_alarms

    run_site_check(cur, soc=88.1)
    assert "SOC_HIGH" in bess.active_alarms

    run_site_check(cur, soc=88.0)
    assert "SOC_HIGH" not in bess.active_alarms
    assert "SOC_HIGH" in alarm_clears(cur)


def test_soc_high_and_critical_high_can_coexist():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    run_site_check(cur, soc=94.0)
    assert "SOC_HIGH" in bess.active_alarms

    run_site_check(cur, soc=95.0)
    assert "SOC_HIGH" in bess.active_alarms
    assert "SOC_CRITICAL_HIGH" in bess.active_alarms

    run_site_check(cur, soc=94.0)
    assert "SOC_CRITICAL_HIGH" in bess.active_alarms

    run_site_check(cur, soc=93.0)
    assert "SOC_CRITICAL_HIGH" not in bess.active_alarms
    assert "SOC_HIGH" in bess.active_alarms


def test_soc_low_and_critical_low_can_coexist():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    run_site_check(cur, soc=10.0)
    assert "SOC_LOW" in bess.active_alarms

    run_site_check(cur, soc=5.0)
    assert "SOC_LOW" in bess.active_alarms
    assert "SOC_CRITICAL_LOW" in bess.active_alarms

    run_site_check(cur, soc=6.0)
    assert "SOC_CRITICAL_LOW" in bess.active_alarms

    run_site_check(cur, soc=7.0)
    assert "SOC_CRITICAL_LOW" not in bess.active_alarms
    assert "SOC_LOW" in bess.active_alarms

    run_site_check(cur, soc=12.0)
    assert "SOC_LOW" not in bess.active_alarms


def test_temperature_high_and_critical_hysteresis_can_coexist():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    run_site_check(cur, temp_c=34.9)
    assert "TEMP_HIGH" not in bess.active_alarms

    run_site_check(cur, temp_c=35.0)
    assert "TEMP_HIGH" in bess.active_alarms

    run_site_check(cur, temp_c=45.0)
    assert "TEMP_HIGH" in bess.active_alarms
    assert "TEMP_CRITICAL" in bess.active_alarms

    run_site_check(cur, temp_c=43.0)
    assert "TEMP_CRITICAL" in bess.active_alarms

    run_site_check(cur, temp_c=42.0)
    assert "TEMP_CRITICAL" not in bess.active_alarms
    assert "TEMP_HIGH" in bess.active_alarms

    run_site_check(cur, temp_c=33.0)
    assert "TEMP_HIGH" not in bess.active_alarms


def test_dc_bus_high_and_low_hysteresis():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    run_site_check(cur, vdc=849.9)
    assert "DC_BUS_HIGH" not in bess.active_alarms

    run_site_check(cur, vdc=850.0)
    assert "DC_BUS_HIGH" in bess.active_alarms

    run_site_check(cur, vdc=845.0)
    assert "DC_BUS_HIGH" in bess.active_alarms

    run_site_check(cur, vdc=840.0)
    assert "DC_BUS_HIGH" not in bess.active_alarms

    run_site_check(cur, vdc=750.1)
    assert "DC_BUS_LOW" not in bess.active_alarms

    run_site_check(cur, vdc=750.0)
    assert "DC_BUS_LOW" in bess.active_alarms

    run_site_check(cur, vdc=755.0)
    assert "DC_BUS_LOW" in bess.active_alarms

    run_site_check(cur, vdc=760.0)
    assert "DC_BUS_LOW" not in bess.active_alarms


def test_current_high_and_critical_hysteresis_can_coexist_for_positive_and_negative_current():
    for sign in (1, -1):
        reset_alarm_state()
        cur = FakeCursor(rowcount=1)

        run_site_check(cur, idc=sign * 299.9)
        assert "CURRENT_HIGH" not in bess.active_alarms

        run_site_check(cur, idc=sign * 300.0)
        assert "CURRENT_HIGH" in bess.active_alarms

        run_site_check(cur, idc=sign * 350.0)
        assert "CURRENT_HIGH" in bess.active_alarms
        assert "CURRENT_CRITICAL" in bess.active_alarms

        run_site_check(cur, idc=sign * 330.0)
        assert "CURRENT_CRITICAL" in bess.active_alarms

        run_site_check(cur, idc=sign * 325.0)
        assert "CURRENT_CRITICAL" not in bess.active_alarms
        assert "CURRENT_HIGH" in bess.active_alarms

        run_site_check(cur, idc=sign * 280.0)
        assert "CURRENT_HIGH" not in bess.active_alarms


def test_site_power_shortfall_debounces_and_clears_as_fault():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)

    for _ in range(4):
        bess.update_site_shortfall_alarm(cur, 20.0, 14.0)
        assert "SITE_POWER_SHORTFALL" not in bess.active_alarms

    bess.update_site_shortfall_alarm(cur, 20.0, 14.0)
    assert "SITE_POWER_SHORTFALL" in bess.active_alarms

    inserts = alarm_inserts(cur)
    assert any(params[0] == "SITE_POWER_SHORTFALL" and params[1] == bess.SEVERITY["FAULT"] for params in inserts)

    bess.update_site_shortfall_alarm(cur, 20.0, 17.5)
    assert "SITE_POWER_SHORTFALL" not in bess.active_alarms


def test_idle_command_clears_site_power_shortfall():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)
    bess.active_alarms.add("SITE_POWER_SHORTFALL")
    bess.site_shortfall_counter = 5

    bess.update_site_shortfall_alarm(cur, 0.0, 0.0)

    assert "SITE_POWER_SHORTFALL" not in bess.active_alarms
    assert bess.site_shortfall_counter == 0
    assert "SITE_POWER_SHORTFALL" in alarm_clears(cur)


def test_legacy_noisy_alarms_are_cleared_by_stage1_check():
    reset_alarm_state()
    cur = FakeCursor(rowcount=1)
    legacy_codes = {
        "POWER_LIMITED",
        "CHARGE_AT_HIGH_SOC",
        "DISCHARGE_AT_LOW_SOC",
        "VOLTAGE_HIGH",
        "VOLTAGE_LOW",
        "TEMP_WARNING",
        "CURRENT_WARNING",
    }
    bess.active_alarms.update(legacy_codes)

    run_site_check(cur)

    assert legacy_codes.isdisjoint(bess.active_alarms)
    cleared = set(alarm_clears(cur))
    assert legacy_codes.issubset(cleared)
