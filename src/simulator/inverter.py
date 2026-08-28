try:
    from .models import (
        InverterProfile,
        MODE_IDLE,
        InverterTelemetry,
        clamp,
        default_inverter_profile,
        mode_from_power,
        r2,
    )
except ImportError:
    from models import (
        InverterProfile,
        MODE_IDLE,
        InverterTelemetry,
        clamp,
        default_inverter_profile,
        mode_from_power,
        r2,
    )


class Inverter:
    def __init__(self, inverter_id: int, batteries, profile: InverterProfile | None = None):
        self.inverter_id = inverter_id
        self.batteries = batteries
        self.profile = profile or default_inverter_profile(inverter_id)
        self.fault = False

    @property
    def available(self) -> bool:
        return bool(
            self.profile.available
            and not self.fault
            and all(battery.available for battery in self.batteries)
        )

    @property
    def average_battery_temp_c(self) -> float:
        if not self.batteries:
            return 25.0
        return sum(b.temp_c for b in self.batteries) / len(self.batteries)

    def derate_factor(self) -> float:
        temp_c = self.average_battery_temp_c + self.profile.temp_offset_c
        if temp_c <= self.profile.derate_start_c:
            return 1.0
        if temp_c >= self.profile.derate_stop_c:
            return 0.45
        span = self.profile.derate_stop_c - self.profile.derate_start_c
        return clamp(1.0 - ((temp_c - self.profile.derate_start_c) / span) * 0.55, 0.45, 1.0)

    def charge_capacity_kw(self) -> float:
        if not self.available:
            return 0.0
        battery_dc_cap = sum(b.charge_capacity_kw() for b in self.batteries)
        battery_ac_cap = battery_dc_cap * self.profile.efficiency
        inverter_cap = min(self.profile.max_charge_kw, self.profile.rated_kw)
        return min(inverter_cap, battery_ac_cap) * self.derate_factor()

    def discharge_capacity_kw(self) -> float:
        if not self.available:
            return 0.0
        battery_dc_cap = sum(b.discharge_capacity_kw() for b in self.batteries)
        battery_ac_cap = battery_dc_cap / self.profile.efficiency
        inverter_cap = min(self.profile.max_discharge_kw, self.profile.rated_kw)
        return min(inverter_cap, battery_ac_cap) * self.derate_factor()

    def ac_to_dc_kw(self, p_ac_kw: float) -> float:
        if p_ac_kw >= 0:
            return p_ac_kw / self.profile.efficiency
        return p_ac_kw * self.profile.efficiency

    def step(self, p_set_kw: float, battery_dc_setpoints_kw, dt_seconds: float):
        battery_telemetry = []
        bat_fault_any = False

        for battery, requested_p_dc_kw in zip(self.batteries, battery_dc_setpoints_kw):
            p_dc_kw = 0.0 if battery.fault else requested_p_dc_kw
            telemetry = battery.step(p_dc_kw, dt_seconds)
            battery_telemetry.append(telemetry)
            bat_fault_any = bat_fault_any or telemetry.fault

        vdc_inv = sum(b.vdc for b in battery_telemetry) / len(battery_telemetry)
        idc_inv = sum(b.idc for b in battery_telemetry)
        temp_inv = sum(b.temp_c for b in battery_telemetry) / len(battery_telemetry)
        p_dc_inv = sum(b.p_dc_kw for b in battery_telemetry)

        if p_dc_inv >= 0:
            p_ac_inv = p_dc_inv * self.profile.efficiency
        else:
            p_ac_inv = p_dc_inv / self.profile.efficiency

        if not self.available or bat_fault_any:
            mode_inv = MODE_IDLE
            fault_inv = True
            p_ac_inv = 0.0
        else:
            mode_inv = mode_from_power(p_ac_inv)
            fault_inv = False

        inverter_telemetry = InverterTelemetry(
            inverter_id=self.inverter_id,
            mode=int(mode_inv),
            p_set_kw=r2(p_set_kw),
            p_actual_kw=r2(p_ac_inv),
            vdc=r2(vdc_inv),
            idc=r2(idc_inv),
            temp_c=r2(temp_inv),
            fault=bool(fault_inv),
        )

        return inverter_telemetry, battery_telemetry, p_ac_inv
