"""Time-of-use arbitrage strategy for the BESS EMS.

Charge when energy is cheap, discharge when it is expensive, hold otherwise.
Hysteresis stop-bands prevent flapping around a threshold, and SOC guard
bands taper power linearly so the site never slams into its SOC limits.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    charge_below: float = 40.0        # $/MWh — start charging under this
    stop_charge_above: float = 55.0   # $/MWh — hysteresis exit for charging
    discharge_above: float = 120.0    # $/MWh — start discharging over this
    stop_discharge_below: float = 95.0  # $/MWh — hysteresis exit for discharging
    charge_kw: float = 150.0
    discharge_kw: float = 150.0
    soc_min: float = 15.0             # % — never discharge below
    soc_max: float = 90.0             # % — never charge above
    taper_band_pct: float = 5.0       # % of SOC over which power ramps to zero
    min_power_kw: float = 5.0         # below this, command IDLE instead


def config_from_env() -> StrategyConfig:
    def f(name, default):
        return float(os.getenv(name, str(default)))

    return StrategyConfig(
        charge_below=f("EMS_CHARGE_BELOW", 40.0),
        stop_charge_above=f("EMS_STOP_CHARGE_ABOVE", 55.0),
        discharge_above=f("EMS_DISCHARGE_ABOVE", 120.0),
        stop_discharge_below=f("EMS_STOP_DISCHARGE_BELOW", 95.0),
        charge_kw=f("EMS_CHARGE_KW", 150.0),
        discharge_kw=f("EMS_DISCHARGE_KW", 150.0),
        soc_min=f("EMS_SOC_MIN", 15.0),
        soc_max=f("EMS_SOC_MAX", 90.0),
        taper_band_pct=f("EMS_TAPER_BAND_PCT", 5.0),
        min_power_kw=f("EMS_MIN_POWER_KW", 5.0),
    )


@dataclass(frozen=True)
class Decision:
    mode: str          # CHARGE | DISCHARGE | IDLE
    p_kw: float        # unsigned magnitude, matches bess_commands convention
    target_soc: float | None
    reasoning: str


def _charge_taper(soc: float, cfg: StrategyConfig) -> float:
    """Scale factor 0..1 for charging as SOC approaches soc_max."""
    headroom = cfg.soc_max - soc
    if headroom <= 0:
        return 0.0
    if headroom >= cfg.taper_band_pct:
        return 1.0
    return headroom / cfg.taper_band_pct


def _discharge_taper(soc: float, cfg: StrategyConfig) -> float:
    """Scale factor 0..1 for discharging as SOC approaches soc_min."""
    headroom = soc - cfg.soc_min
    if headroom <= 0:
        return 0.0
    if headroom >= cfg.taper_band_pct:
        return 1.0
    return headroom / cfg.taper_band_pct


def decide(
    soc: float,
    price: float,
    last_mode: str,
    cfg: StrategyConfig,
    critical_alarms: int = 0,
) -> Decision:
    """Evaluate one EMS control decision."""
    if critical_alarms > 0:
        return Decision(
            "IDLE", 0.0, None,
            f"Safety stand-down: {critical_alarms} active CRITICAL alarm(s)",
        )

    # Hysteresis: which regime does this price put us in, given where we were?
    if last_mode == "CHARGE":
        want_charge = price < cfg.stop_charge_above
        want_discharge = price > cfg.discharge_above
    elif last_mode == "DISCHARGE":
        want_discharge = price > cfg.stop_discharge_below
        want_charge = price < cfg.charge_below
    else:
        want_charge = price < cfg.charge_below
        want_discharge = price > cfg.discharge_above

    if want_discharge:
        taper = _discharge_taper(soc, cfg)
        p_kw = round(cfg.discharge_kw * taper, 1)
        if p_kw < cfg.min_power_kw:
            return Decision(
                "IDLE", 0.0, cfg.soc_min,
                f"Price {price:.1f} $/MWh favours discharge but SOC {soc:.1f}% "
                f"is at/near floor {cfg.soc_min:.0f}% - holding",
            )
        return Decision(
            "DISCHARGE", p_kw, cfg.soc_min,
            f"Price {price:.1f} $/MWh >= sell threshold - discharging {p_kw:.0f} kW "
            f"(SOC {soc:.1f}%, floor {cfg.soc_min:.0f}%)",
        )

    if want_charge:
        taper = _charge_taper(soc, cfg)
        p_kw = round(cfg.charge_kw * taper, 1)
        if p_kw < cfg.min_power_kw:
            return Decision(
                "IDLE", 0.0, cfg.soc_max,
                f"Price {price:.1f} $/MWh favours charge but SOC {soc:.1f}% "
                f"is at/near ceiling {cfg.soc_max:.0f}% - holding",
            )
        return Decision(
            "CHARGE", p_kw, cfg.soc_max,
            f"Price {price:.1f} $/MWh <= buy threshold - charging {p_kw:.0f} kW "
            f"(SOC {soc:.1f}%, ceiling {cfg.soc_max:.0f}%)",
        )

    return Decision(
        "IDLE", 0.0, None,
        f"Price {price:.1f} $/MWh in dead band "
        f"({cfg.charge_below:.0f}-{cfg.discharge_above:.0f} $/MWh) - holding",
    )
