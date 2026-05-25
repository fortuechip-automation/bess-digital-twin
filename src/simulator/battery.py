import random

try:
    from .models import (
        BAT_ROUNDTRIP_EFF,
        BatteryProfile,
        BatteryTelemetry,
        clamp,
        default_battery_profile,
        r2,
    )
except ImportError:
    from models import (
        BAT_ROUNDTRIP_EFF,
        BatteryProfile,
        BatteryTelemetry,
        clamp,
        default_battery_profile,
        r2,
    )


class BatteryUnit:
    def __init__(
        self,
        battery_id: int,
        capacity_kwh: float,
        soc: float | None = None,
        profile: BatteryProfile | None = None,
    ):
        self.profile = profile or default_battery_profile(battery_id, capacity_kwh)
        self.battery_id = battery_id
        self.capacity_kwh = self.profile.capacity_kwh
        initial_soc = 50.0 + self.profile.dispatch_weight + (((battery_id * 17) % 13) - 6) * 0.18
        self.soc = initial_soc if soc is None else float(soc)
        self.temp_c = 25.0 + self.profile.temp_offset_c
        self.fault = False

    @property
    def available(self) -> bool:
        return bool(self.profile.available and not self.fault)

    def charge_capacity_kw(self) -> float:
        if not self.available:
            return 0.0
        headroom = clamp((self.profile.soc_max - self.soc) / 10.0, 0.0, 1.0)
        soh_factor = clamp(self.profile.soh_percent / 100.0, 0.0, 1.0)
        return self.profile.max_charge_kw * headroom * soh_factor

    def discharge_capacity_kw(self) -> float:
        if not self.available:
            return 0.0
        headroom = clamp((self.soc - self.profile.soc_min) / 10.0, 0.0, 1.0)
        soh_factor = clamp(self.profile.soh_percent / 100.0, 0.0, 1.0)
        return self.profile.max_discharge_kw * headroom * soh_factor

    def step(self, p_dc_kw: float, dt_hours: float) -> BatteryTelemetry:
        if not self.available:
            p_dc_kw = 0.0
        elif p_dc_kw >= 0:
            p_dc_kw = clamp(p_dc_kw, 0.0, self.charge_capacity_kw())
        else:
            p_dc_kw = clamp(p_dc_kw, -self.discharge_capacity_kw(), 0.0)

        if p_dc_kw >= 0:
            energy_change_kwh = p_dc_kw * dt_hours * BAT_ROUNDTRIP_EFF
        else:
            energy_change_kwh = p_dc_kw * dt_hours / BAT_ROUNDTRIP_EFF

        soc_new = self.soc + (energy_change_kwh / self.capacity_kwh) * 100.0
        self.soc = clamp(soc_new, 0.0, 100.0)

        noise = random.uniform(-self.profile.sensor_noise, self.profile.sensor_noise)
        vdc = 760.0 + (840.0 - 760.0) * (self.soc / 100.0) + self.profile.voltage_offset_v + noise
        idc = 0.0 if abs(vdc) < 1e-6 else (p_dc_kw * 1000.0 / vdc)
        load_factor = abs(p_dc_kw) / max(self.profile.max_charge_kw, self.profile.max_discharge_kw, 1.0)
        target_temp = 24.0 + self.profile.temp_offset_c + load_factor * self.profile.thermal_gain
        self.temp_c += (target_temp - self.temp_c) * 0.18
        temp_c = self.temp_c + random.uniform(-0.15, 0.15)

        return BatteryTelemetry(
            battery_id=self.battery_id,
            soc=r2(self.soc),
            vdc=r2(vdc),
            idc=r2(idc),
            p_dc_kw=r2(p_dc_kw),
            temp_c=r2(temp_c),
            fault=bool(self.fault),
        )
