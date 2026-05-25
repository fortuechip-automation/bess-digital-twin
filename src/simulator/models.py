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


@dataclass(frozen=True)
class BatteryProfile:
    battery_id: int
    capacity_kwh: float
    max_charge_kw: float
    max_discharge_kw: float
    soc_min: float
    soc_max: float
    soh_percent: float
    voltage_offset_v: float
    temp_offset_c: float
    thermal_gain: float
    sensor_noise: float
    dispatch_weight: float
    available: bool = True


@dataclass(frozen=True)
class InverterProfile:
    inverter_id: int
    rated_kw: float
    max_charge_kw: float
    max_discharge_kw: float
    efficiency: float
    # Reserved for the next transient-response phase.
    ramp_rate_kw_per_sec: float
    response_lag: float
    temp_offset_c: float
    derate_start_c: float
    derate_stop_c: float
    dispatch_weight: float
    available: bool = True


def default_battery_profile(battery_id: int, base_capacity_kwh: float) -> BatteryProfile:
    """Create stable per-battery variation without external config."""
    pattern = ((battery_id * 37) % 11) - 5
    fine_pattern = ((battery_id * 19) % 7) - 3
    return BatteryProfile(
        battery_id=battery_id,
        capacity_kwh=base_capacity_kwh * (1.0 + pattern * 0.006),
        max_charge_kw=BAT_MAX_KW * (0.90 + ((battery_id * 5) % 9) * 0.015),
        max_discharge_kw=BAT_MAX_KW * (0.92 + ((battery_id * 7) % 8) * 0.012),
        soc_min=5.0 + (battery_id % 3) * 0.5,
        soc_max=95.0 - (battery_id % 4) * 0.4,
        soh_percent=96.0 + ((battery_id * 13) % 5),
        voltage_offset_v=pattern * 0.8,
        temp_offset_c=fine_pattern * 0.35,
        thermal_gain=4.2 + ((battery_id * 3) % 6) * 0.35,
        sensor_noise=0.35 + (battery_id % 4) * 0.08,
        dispatch_weight=0.92 + ((battery_id * 11) % 9) * 0.02,
        available=True,
    )


def default_inverter_profile(inverter_id: int) -> InverterProfile:
    """Create stable per-inverter variation without external config."""
    pattern = ((inverter_id * 29) % 9) - 4
    return InverterProfile(
        inverter_id=inverter_id,
        rated_kw=INV_MAX_KW * (0.95 + ((inverter_id * 3) % 6) * 0.015),
        max_charge_kw=INV_MAX_KW * (0.90 + ((inverter_id * 5) % 8) * 0.018),
        max_discharge_kw=INV_MAX_KW * (0.91 + ((inverter_id * 7) % 7) * 0.016),
        efficiency=clamp(INV_EFF + pattern * 0.002, 0.955, 0.98),
        ramp_rate_kw_per_sec=35.0 + (inverter_id % 5) * 5.0,
        response_lag=0.08 + (inverter_id % 4) * 0.03,
        temp_offset_c=pattern * 0.45,
        derate_start_c=36.0 + (inverter_id % 3),
        derate_stop_c=46.0 + (inverter_id % 4),
        dispatch_weight=0.90 + ((inverter_id * 13) % 10) * 0.025,
        available=True,
    )


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
