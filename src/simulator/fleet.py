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
        default_battery_profile,
        default_inverter_profile,
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
        default_battery_profile,
        default_inverter_profile,
        mode_from_power,
        r2,
    )


def allocate_signed_power(requested_kw: float, assets) -> dict:
    if not assets or abs(requested_kw) < 1e-9:
        return {asset["id"]: 0.0 for asset in assets}

    direction = 1.0 if requested_kw > 0 else -1.0
    remaining_kw = abs(requested_kw)
    allocations = {asset["id"]: 0.0 for asset in assets}
    open_assets = list(assets)

    while open_assets and remaining_kw > 1e-6:
        total_weight = sum(max(asset["weight"], 0.0) for asset in open_assets)
        if total_weight <= 0.0:
            break

        next_open = []
        allocated_this_round = 0.0

        for asset in open_assets:
            asset_id = asset["id"]
            headroom_kw = max(asset["capacity_kw"] - allocations[asset_id], 0.0)
            if headroom_kw <= 1e-6:
                continue

            share_kw = remaining_kw * (max(asset["weight"], 0.0) / total_weight)
            added_kw = min(share_kw, headroom_kw)
            allocations[asset_id] += added_kw
            allocated_this_round += added_kw

            if headroom_kw - added_kw > 1e-6:
                next_open.append(asset)

        if allocated_this_round <= 1e-6:
            break
        remaining_kw -= allocated_this_round
        open_assets = next_open

    return {asset_id: r2(direction * value) for asset_id, value in allocations.items()}


class BESSFleet:
    def __init__(self, n_inverters: int = N_INVERTERS, n_batteries: int = N_BATTERIES):
        if n_batteries != n_inverters * 2:
            raise ValueError("BESSFleet currently expects exactly two batteries per inverter")

        self.n_inverters = n_inverters
        self.n_batteries = n_batteries
        per_bat_capacity_kwh = SITE_CAPACITY_KWH / n_batteries
        self.batteries = []
        for i in range(n_batteries):
            battery_id = i + 1
            profile = default_battery_profile(battery_id, per_bat_capacity_kwh)
            self.batteries.append(
                BatteryUnit(
                    battery_id=battery_id,
                    capacity_kwh=per_bat_capacity_kwh,
                    profile=profile,
                )
            )

        self.inverters = []
        for i in range(n_inverters):
            inverter_id = i + 1
            profile = default_inverter_profile(inverter_id)
            self.inverters.append(
                Inverter(
                    inverter_id=inverter_id,
                    batteries=self.batteries[2 * i : 2 * i + 2],
                    profile=profile,
                )
            )

    @property
    def average_soc(self) -> float:
        return sum(b.soc for b in self.batteries) / self.n_batteries

    def step(self, site_p_set_kw: float):
        site_p_set_limited = clamp(
            site_p_set_kw,
            SITE_MAX_DISCHARGE_KW,
            SITE_MAX_CHARGE_KW,
        )

        dt_hours = TELEMETRY_INTERVAL / 3600.0
        inverter_dispatch = self._dispatch_inverters(site_p_set_limited)

        inv_rows = []
        bat_rows = []
        p_actual_site = 0.0
        vdc_site_list = []
        temp_site_list = []

        for inverter in self.inverters:
            inv_set_kw = inverter_dispatch.get(inverter.inverter_id, 0.0)
            battery_dc_setpoints = self._dispatch_batteries(inverter, inv_set_kw)
            inv_telemetry, battery_telemetry, p_ac_inv = inverter.step(
                p_set_kw=inv_set_kw,
                battery_dc_setpoints_kw=battery_dc_setpoints,
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

    def _dispatch_inverters(self, site_p_set_limited: float) -> dict[int, float]:
        assets = []
        charging = site_p_set_limited >= 0
        for inverter in self.inverters:
            capacity_kw = inverter.charge_capacity_kw() if charging else inverter.discharge_capacity_kw()
            if capacity_kw <= 0.0:
                continue
            assets.append(
                {
                    "id": inverter.inverter_id,
                    "capacity_kw": capacity_kw,
                    "weight": capacity_kw * inverter.profile.dispatch_weight,
                }
            )

        allocations = allocate_signed_power(site_p_set_limited, assets)
        return {inverter.inverter_id: allocations.get(inverter.inverter_id, 0.0) for inverter in self.inverters}

    def _dispatch_batteries(self, inverter, inv_set_kw: float) -> list[float]:
        requested_dc_kw = inverter.ac_to_dc_kw(inv_set_kw)
        charging = requested_dc_kw >= 0
        assets = []

        for battery in inverter.batteries:
            capacity_kw = battery.charge_capacity_kw() if charging else battery.discharge_capacity_kw()
            capacity_kw = min(capacity_kw, BAT_MAX_KW)
            if capacity_kw <= 0.0:
                continue
            assets.append(
                {
                    "id": battery.battery_id,
                    "capacity_kw": capacity_kw,
                    "weight": capacity_kw * battery.profile.dispatch_weight,
                }
            )

        allocations = allocate_signed_power(requested_dc_kw, assets)
        return [allocations.get(battery.battery_id, 0.0) for battery in inverter.batteries]
