"""
Alarm bits: one true/false OPC tag per simulator alarm.

The simulator decides when an alarm is active (thresholds and hysteresis live in
src/simulator/bess.py) and records it in the bess_alarms table. The bridge turns
the list of active alarm codes into one Boolean per code, the way a battery
system or inverter exposes alarm bits to SCADA. Ignition then puts an alarm on
each bit, so every plant alarm reaches the header and alarm tables by name.

This file holds only the catalogue and pure logic, so it can be tested without
an OPC server or a database.
"""

# Site-level alarm codes, plus the fleet-wide SOC imbalance alarm.
# Must match the codes raised in src/simulator/bess.py.
SITE_ALARM_CODES = (
    "SOC_LOW",
    "SOC_HIGH",
    "SOC_CRITICAL_LOW",
    "SOC_CRITICAL_HIGH",
    "TEMP_HIGH",
    "TEMP_CRITICAL",
    "DC_BUS_LOW",
    "DC_BUS_HIGH",
    "CURRENT_HIGH",
    "CURRENT_CRITICAL",
    "SITE_POWER_SHORTFALL",
    "BATTERY_SOC_IMBALANCE",
)

# Every inverter and battery can raise these three, coded e.g. INV03_TEMP_HIGH.
EQUIPMENT_ALARM_SUFFIXES = ("TEMP_HIGH", "TEMP_CRITICAL", "UNAVAILABLE")


def equipment_name(prefix: str, equipment_id: int) -> str:
    """INV + 3 -> 'INV03'. Same format as the simulator and the OPC folders."""
    return f"{prefix}{int(equipment_id):02d}"


def alarm_bit_catalogue(n_inverters: int, n_batteries: int):
    """
    Every alarm bit the bridge publishes, as (alarm_code, folder_path, tag_name).

    folder_path is where the bit lives in the OPC tree, e.g.
      ('SOC_LOW',          'BESS1/Site/Alarms',                'SOC_LOW')
      ('INV03_TEMP_HIGH',  'BESS1/Inverters/INV03/Alarms',     'TEMP_HIGH')
    """
    bits = [(code, "BESS1/Site/Alarms", code) for code in SITE_ALARM_CODES]
    for group, prefix, count in (("Inverters", "INV", n_inverters), ("Batteries", "BAT", n_batteries)):
        for i in range(1, count + 1):
            name = equipment_name(prefix, i)
            for suffix in EQUIPMENT_ALARM_SUFFIXES:
                bits.append((f"{name}_{suffix}", f"BESS1/{group}/{name}/Alarms", suffix))
    return bits


def alarm_bit_states(active_codes, catalogue):
    """Map each catalogue alarm code to True (active) or False (clear)."""
    active = set(active_codes)
    return {code: code in active for code, _folder, _name in catalogue}


def unknown_active_codes(active_codes, catalogue):
    """Active codes with no bit in the catalogue (the simulator gained an alarm the bridge doesn't know)."""
    known = {code for code, _folder, _name in catalogue}
    return sorted(set(active_codes) - known)
