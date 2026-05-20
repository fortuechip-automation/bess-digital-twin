import random

try:
    from .models import (
        BAT_ROUNDTRIP_EFF,
        BatteryTelemetry,
        clamp,
        r2,
    )
except ImportError:
    from models import (
        BAT_ROUNDTRIP_EFF,
        BatteryTelemetry,
        clamp,
        r2,
    )


class BatteryUnit:
    def __init__(self, battery_id: int, capacity_kwh: float, soc: float | None = None):
        self.battery_id = battery_id
        self.capacity_kwh = capacity_kwh
        self.soc = 50.0 + random.uniform(-2, 2) if soc is None else float(soc)
        self.fault = False

    def step(self, p_dc_kw: float, dt_hours: float) -> BatteryTelemetry:
        if self.fault:
            p_dc_kw = 0.0

        if p_dc_kw >= 0:
            energy_change_kwh = p_dc_kw * dt_hours * BAT_ROUNDTRIP_EFF
        else:
            energy_change_kwh = p_dc_kw * dt_hours / BAT_ROUNDTRIP_EFF

        soc_new = self.soc + (energy_change_kwh / self.capacity_kwh) * 100.0
        self.soc = clamp(soc_new, 0.0, 100.0)

        vdc = 760.0 + (840.0 - 760.0) * (self.soc / 100.0) + random.uniform(-2.0, 2.0)
        idc = 0.0 if abs(vdc) < 1e-6 else (p_dc_kw * 1000.0 / vdc)
        temp_c = 25.0 + (abs(p_dc_kw) / 250.0) * 5.0 + random.uniform(-0.5, 0.5)

        return BatteryTelemetry(
            battery_id=self.battery_id,
            soc=r2(self.soc),
            vdc=r2(vdc),
            idc=r2(idc),
            p_dc_kw=r2(p_dc_kw),
            temp_c=r2(temp_c),
            fault=bool(self.fault),
        )
