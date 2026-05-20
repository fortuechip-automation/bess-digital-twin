try:
    from .battery import BatteryUnit
    from .inverter import Inverter
    from .models import (
        BAT_MAX_KW,
        N_BATTERIES,
        N_INVERTERS,
        SITE_CAPACITY_KWH,
        SITE_MAX_CHARGE_KW,
        SITE_MAX_DISCHARGE_KW,
        TELEMETRY_INTERVAL,
        SiteTelemetry,
        clamp,
        mode_from_power,
        r2,
    )
except ImportError:
    from battery import BatteryUnit
    from inverter import Inverter
    from models import (
        BAT_MAX_KW,
        N_BATTERIES,
        N_INVERTERS,
        SITE_CAPACITY_KWH,
        SITE_MAX_CHARGE_KW,
        SITE_MAX_DISCHARGE_KW,
        TELEMETRY_INTERVAL,
        SiteTelemetry,
        clamp,
        mode_from_power,
        r2,
    )


class BESSFleet:
    def __init__(self, n_inverters: int = N_INVERTERS, n_batteries: int = N_BATTERIES):
        if n_batteries != n_inverters * 2:
            raise ValueError("BESSFleet currently expects exactly two batteries per inverter")

        self.n_inverters = n_inverters
        self.n_batteries = n_batteries
        per_bat_capacity_kwh = SITE_CAPACITY_KWH / n_batteries
        self.batteries = [
            BatteryUnit(battery_id=i + 1, capacity_kwh=per_bat_capacity_kwh)
            for i in range(n_batteries)
        ]
        self.inverters = [
            Inverter(inverter_id=i + 1, batteries=self.batteries[2 * i : 2 * i + 2])
            for i in range(n_inverters)
        ]

    @property
    def average_soc(self) -> float:
        return sum(b.soc for b in self.batteries) / self.n_batteries

    def step(self, site_p_set_kw: float):
        site_p_set_limited = clamp(
            site_p_set_kw,
            SITE_MAX_DISCHARGE_KW,
            SITE_MAX_CHARGE_KW,
        )

        per_inv_set = site_p_set_limited / self.n_inverters if self.n_inverters else 0.0
        dt_hours = TELEMETRY_INTERVAL / 3600.0

        inv_rows = []
        bat_rows = []
        p_actual_site = 0.0
        vdc_site_list = []
        temp_site_list = []

        for inverter in self.inverters:
            inv_set_kw = 0.0 if inverter.fault else per_inv_set
            per_bat_dc_kw = clamp(inv_set_kw / 2.0, -BAT_MAX_KW, BAT_MAX_KW)
            inv_telemetry, battery_telemetry, p_ac_inv = inverter.step(
                p_set_kw=inv_set_kw,
                per_bat_dc_kw=per_bat_dc_kw,
                dt_hours=dt_hours,
            )

            inv_rows.append(inv_telemetry.as_db_row())
            bat_rows.extend(b.as_db_row() for b in battery_telemetry)

            p_actual_site += p_ac_inv
            vdc_site_list.append(inv_telemetry.vdc)
            temp_site_list.append(inv_telemetry.temp_c)

        soc_site = self.average_soc
        vdc_site = sum(vdc_site_list) / len(vdc_site_list) if vdc_site_list else 800.0
        temp_site = sum(temp_site_list) / len(temp_site_list) if temp_site_list else 25.0
        idc_site = 0.0 if abs(vdc_site) < 1e-6 else (p_actual_site * 1000.0 / vdc_site)
        mode_site = mode_from_power(p_actual_site)

        site = SiteTelemetry(
            soc=r2(soc_site),
            mode=int(mode_site),
            p_set_kw=r2(site_p_set_kw),
            p_actual_kw=r2(p_actual_site),
            vdc=r2(vdc_site),
            idc=r2(idc_site),
            temp_c=r2(temp_site),
        )

        return inv_rows, bat_rows, site.as_db_row()
