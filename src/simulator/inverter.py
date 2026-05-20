try:
    from .models import (
        INV_EFF,
        MODE_IDLE,
        InverterTelemetry,
        mode_from_power,
        r2,
    )
except ImportError:
    from models import (
        INV_EFF,
        MODE_IDLE,
        InverterTelemetry,
        mode_from_power,
        r2,
    )


class Inverter:
    def __init__(self, inverter_id: int, batteries):
        self.inverter_id = inverter_id
        self.batteries = batteries
        self.fault = False

    def step(self, p_set_kw: float, per_bat_dc_kw: float, dt_hours: float):
        battery_telemetry = []
        bat_fault_any = False

        for battery in self.batteries:
            p_dc_kw = 0.0 if battery.fault else per_bat_dc_kw
            telemetry = battery.step(p_dc_kw, dt_hours)
            battery_telemetry.append(telemetry)
            bat_fault_any = bat_fault_any or telemetry.fault

        vdc_inv = sum(b.vdc for b in battery_telemetry) / len(battery_telemetry)
        idc_inv = sum(b.idc for b in battery_telemetry)
        temp_inv = sum(b.temp_c for b in battery_telemetry) / len(battery_telemetry)
        p_dc_inv = per_bat_dc_kw * len(battery_telemetry)

        if p_dc_inv >= 0:
            p_ac_inv = p_dc_inv * INV_EFF
        else:
            p_ac_inv = p_dc_inv / INV_EFF

        if self.fault or bat_fault_any:
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
