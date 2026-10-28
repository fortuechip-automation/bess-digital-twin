"""Alarm bits: the catalogue must cover every alarm the simulator can raise."""

import re
from pathlib import Path

from src.opcua_bridge.alarm_bits import (
    SITE_ALARM_CODES,
    alarm_bit_catalogue,
    alarm_bit_states,
    unknown_active_codes,
)

CATALOGUE = alarm_bit_catalogue(n_inverters=10, n_batteries=20)


def test_catalogue_has_102_bits():
    # 12 site + 10 inverters x 3 + 20 batteries x 3
    assert len(CATALOGUE) == 102
    assert len({code for code, _f, _n in CATALOGUE}) == 102


def test_equipment_bits_sit_under_their_own_folder():
    assert ("INV03_TEMP_HIGH", "BESS1/Inverters/INV03/Alarms", "TEMP_HIGH") in CATALOGUE
    assert ("BAT20_UNAVAILABLE", "BESS1/Batteries/BAT20/Alarms", "UNAVAILABLE") in CATALOGUE
    assert ("BATTERY_SOC_IMBALANCE", "BESS1/Site/Alarms", "BATTERY_SOC_IMBALANCE") in CATALOGUE


def test_states_follow_active_codes():
    states = alarm_bit_states({"BATTERY_SOC_IMBALANCE", "BAT15_TEMP_HIGH"}, CATALOGUE)
    assert states["BATTERY_SOC_IMBALANCE"] is True
    assert states["BAT15_TEMP_HIGH"] is True
    assert states["BAT15_TEMP_CRITICAL"] is False
    assert sum(states.values()) == 2


def test_unknown_codes_are_reported():
    assert unknown_active_codes({"SOC_LOW", "MADE_UP_ALARM"}, CATALOGUE) == ["MADE_UP_ALARM"]


def test_site_codes_match_the_simulator():
    """Every site alarm code the simulator raises (not legacy clears) has a bit."""
    source = Path("src/simulator/bess.py").read_text()
    raised = set(re.findall(r'check_hysteresis_alarm\(\s*cur,\s*"([A-Z_]+)"', source))
    raised |= set(re.findall(r'^\s*"(SITE_POWER_SHORTFALL)",', source, re.M))
    assert raised, "pattern found nothing; the simulator's alarm code layout changed"
    assert raised <= set(SITE_ALARM_CODES)
