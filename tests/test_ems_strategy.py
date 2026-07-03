from datetime import datetime, timezone

from src.ems.market import (
    MARKET_PRICE_CAP,
    MARKET_PRICE_FLOOR,
    base_price_for_local_hour,
    interval_start,
    simulated_price,
)
from src.ems.strategy import Decision, StrategyConfig, decide

CFG = StrategyConfig()


def test_charges_when_price_low():
    d = decide(soc=50.0, price=25.0, last_mode="IDLE", cfg=CFG)
    assert d.mode == "CHARGE"
    assert d.p_kw == CFG.charge_kw
    assert d.target_soc == CFG.soc_max


def test_discharges_when_price_high():
    d = decide(soc=50.0, price=180.0, last_mode="IDLE", cfg=CFG)
    assert d.mode == "DISCHARGE"
    assert d.p_kw == CFG.discharge_kw
    assert d.target_soc == CFG.soc_min


def test_idles_in_dead_band():
    d = decide(soc=50.0, price=70.0, last_mode="IDLE", cfg=CFG)
    assert d.mode == "IDLE"
    assert d.p_kw == 0.0


def test_hysteresis_keeps_charging_past_entry_threshold():
    # Price rose above charge_below but is still under stop_charge_above.
    d = decide(soc=50.0, price=48.0, last_mode="CHARGE", cfg=CFG)
    assert d.mode == "CHARGE"


def test_hysteresis_exit_stops_charging():
    d = decide(soc=50.0, price=60.0, last_mode="CHARGE", cfg=CFG)
    assert d.mode == "IDLE"


def test_hysteresis_keeps_discharging_past_entry_threshold():
    d = decide(soc=50.0, price=100.0, last_mode="DISCHARGE", cfg=CFG)
    assert d.mode == "DISCHARGE"


def test_discharge_tapers_near_soc_floor():
    d = decide(soc=CFG.soc_min + 2.5, price=180.0, last_mode="IDLE", cfg=CFG)
    assert d.mode == "DISCHARGE"
    assert 0 < d.p_kw < CFG.discharge_kw


def test_no_discharge_at_soc_floor():
    d = decide(soc=CFG.soc_min, price=180.0, last_mode="IDLE", cfg=CFG)
    assert d.mode == "IDLE"


def test_no_charge_at_soc_ceiling():
    d = decide(soc=CFG.soc_max, price=10.0, last_mode="IDLE", cfg=CFG)
    assert d.mode == "IDLE"


def test_critical_alarm_forces_stand_down():
    d = decide(soc=50.0, price=180.0, last_mode="DISCHARGE", cfg=CFG, critical_alarms=2)
    assert d.mode == "IDLE"
    assert "stand-down" in d.reasoning.lower()


def test_price_is_deterministic_per_interval():
    iv = interval_start(datetime(2026, 7, 3, 9, 2, 17, tzinfo=timezone.utc))
    assert simulated_price(iv) == simulated_price(iv)


def test_price_within_market_bounds():
    iv = interval_start(datetime(2026, 1, 1, tzinfo=timezone.utc))
    for i in range(288 * 7):  # one simulated week
        ts = datetime.fromtimestamp(iv.timestamp() + i * 300, tz=timezone.utc)
        p = simulated_price(ts)
        assert MARKET_PRICE_FLOOR <= p <= MARKET_PRICE_CAP


def test_daily_shape_has_evening_peak_and_overnight_trough():
    assert base_price_for_local_hour(19.0) > base_price_for_local_hour(3.0)
    assert base_price_for_local_hour(19.0) > base_price_for_local_hour(13.0)
