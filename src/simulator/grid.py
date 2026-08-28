"""Single-area grid frequency model.

The plant does not run in isolation. It sits on a power system whose frequency
is the speedometer of every synchronous machine connected to it: generation
above load speeds the system up, load above generation slows it down. Nothing
in this simulator modelled that, so plant power had nothing to push against and
frequency did not exist as a concept.

The physics is the standard swing equation for a single-area system:

        2H     d(Δf)
       ---- ·  -----  =  ΔP_pu  −  D · Δf_pu
       f_nom     dt

  H   inertia constant, in seconds -- how much energy the system's spinning
      mass stores relative to its rating. Real synchronous systems sit around
      3-6 s; low-inertia (high-renewable) systems are lower and swing faster.
  D   load damping -- real loads draw less power as frequency falls, which
      partially self-corrects an imbalance and sets the steady-state offset.
  ΔP  power imbalance in per-unit of the system base.

Sign convention follows the rest of the simulator: plant power POSITIVE means
CHARGING, which is a load on the system and pushes frequency DOWN. Negative
means discharging, which is generation and pushes frequency UP.
"""

import random
from dataclasses import dataclass

try:
    from .models import clamp, r2
except ImportError:  # pragma: no cover - direct script execution
    from models import clamp, r2


F_NOMINAL_HZ = 50.0

# Beyond this band a real system has tripped protection and the linear swing
# equation stops describing anything useful. Clamp so a runaway stays legible.
F_MIN_HZ = 45.0
F_MAX_HZ = 55.0


@dataclass(frozen=True)
class GridProfile:
    """The character of the power system the plant is connected to.

    `system_base_kw` is the single most important knob. The plant is 250 kW:
    against a 5 MW islanded feeder that is 5% of the system and its response
    visibly moves frequency; against hundreds of MW it is a price-taker and
    frequency is effectively an external input it can only follow. Both are
    real situations for a BESS -- this parameter chooses which one you are
    simulating.
    """

    system_base_kw: float = 5_000.0
    inertia_h_s: float = 4.0
    damping_d: float = 1.5
    f_nominal_hz: float = F_NOMINAL_HZ
    # Ambient load churn, per-unit. Real grid frequency is never exactly
    # nominal -- it wanders continuously. This matters more than it looks:
    # without it a control deadband has nothing to ignore and looks pointless.
    load_noise_pu: float = 0.0005


class GridModel:
    """Frequency of the system the plant is connected to."""

    def __init__(self, profile: GridProfile | None = None, rng: random.Random | None = None):
        self.profile = profile or GridProfile()
        self.rng = rng if rng is not None else random.Random()
        self.frequency_hz = self.profile.f_nominal_hz
        self.rocof_hz_s = 0.0
        # Externally imposed imbalance, in kW, POSITIVE = surplus generation.
        # A generator trip is a negative step; a load rejection a positive one.
        self.disturbance_kw = 0.0

    @property
    def delta_f_hz(self) -> float:
        return self.frequency_hz - self.profile.f_nominal_hz

    def set_disturbance(self, imbalance_kw: float) -> None:
        """Impose a standing power imbalance (negative = generation deficit)."""
        self.disturbance_kw = float(imbalance_kw)

    def step(self, plant_p_kw: float, dt_seconds: float) -> float:
        """Advance the system one timestep and return the new frequency.

        `plant_p_kw` is the plant's ACTUAL power, positive for charging.
        """
        p = self.profile

        noise_pu = self.rng.gauss(0.0, p.load_noise_pu) if p.load_noise_pu else 0.0

        # Charging is a load, so it subtracts from the generation-load balance.
        imbalance_pu = (self.disturbance_kw - plant_p_kw) / p.system_base_kw + noise_pu

        # 2H·d(Δf_pu)/dt = ΔP_pu − D·Δf_pu, converted back into Hz/s.
        delta_f_pu = self.delta_f_hz / p.f_nominal_hz
        self.rocof_hz_s = (
            (imbalance_pu - p.damping_d * delta_f_pu) / (2.0 * p.inertia_h_s)
        ) * p.f_nominal_hz

        self.frequency_hz = clamp(
            self.frequency_hz + self.rocof_hz_s * dt_seconds, F_MIN_HZ, F_MAX_HZ
        )
        return self.frequency_hz

    def as_db_row(self) -> tuple:
        """(freq_hz, rocof_hz_s, disturbance_kw) for grid_status."""
        return (r2(self.frequency_hz), round(self.rocof_hz_s, 4), r2(self.disturbance_kw))
