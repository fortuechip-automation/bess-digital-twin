from dataclasses import dataclass


MODE_IDLE = 1
MODE_CHARGE = 2
MODE_DISCHARGE = 3

TELEMETRY_INTERVAL = 1.0

N_INVERTERS = 10
N_BATTERIES = 20

SITE_CAPACITY_KWH = 1000.0
SITE_MAX_CHARGE_KW = 250.0
SITE_MAX_DISCHARGE_KW = -250.0

INV_MAX_KW = 250.0
BAT_MAX_KW = 150.0

BAT_ROUNDTRIP_EFF = 0.95
INV_EFF = 0.97


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def r2(x: float) -> float:
    return float(round(x, 2))


def mode_from_power(p_kw: float) -> int:
    if abs(p_kw) < 0.5:
        return MODE_IDLE
    return MODE_CHARGE if p_kw > 0 else MODE_DISCHARGE


def map_mode_id_to_text(mode_id: int) -> str:
    if mode_id == MODE_IDLE:
        return "IDLE"
    if mode_id == MODE_CHARGE:
        return "CHARGE"
    if mode_id == MODE_DISCHARGE:
        return "DISCHARGE"
    return "UNKNOWN"


@dataclass
class BatteryTelemetry:
    battery_id: int
    soc: float
    vdc: float
    idc: float
    p_dc_kw: float
    temp_c: float
    fault: bool

    def as_db_row(self):
        return (
            self.battery_id,
            self.soc,
            self.vdc,
            self.idc,
            self.p_dc_kw,
            self.temp_c,
            self.fault,
        )


@dataclass
class InverterTelemetry:
    inverter_id: int
    mode: int
    p_set_kw: float
    p_actual_kw: float
    vdc: float
    idc: float
    temp_c: float
    fault: bool

    def as_db_row(self):
        return (
            self.inverter_id,
            self.mode,
            self.p_set_kw,
            self.p_actual_kw,
            self.vdc,
            self.idc,
            self.temp_c,
            self.fault,
        )


@dataclass
class SiteTelemetry:
    soc: float
    mode: int
    p_set_kw: float
    p_actual_kw: float
    vdc: float
    idc: float
    temp_c: float

    def as_db_row(self):
        return (
            self.soc,
            self.mode,
            self.p_set_kw,
            self.p_actual_kw,
            self.vdc,
            self.idc,
            self.temp_c,
        )
