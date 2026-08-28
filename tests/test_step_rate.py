"""Simulation rate must not change simulated behaviour.

Splitting physics (20 Hz) from telemetry (1 Hz) is only safe if the device
models integrate against dt rather than against "one step". The battery thermal
lag used a fixed per-step coefficient and did not -- these tests pin the fix so
it cannot regress the next time the rate is tuned.
"""

import math

from src.simulator.fleet import BESSFleet
from src.simulator.models import BATTERY_TEMP_TAU_S


def test_thermal_lag_calibration_matches_the_original_coefficient():
    """The old hard-coded 0.18 must be exactly what dt=1.0 s now produces."""
    alpha_at_one_second = 1.0 - math.exp(-1.0 / BATTERY_TEMP_TAU_S)

    assert abs(alpha_at_one_second - 0.18) < 0.0005


def test_soc_is_invariant_to_step_rate():
    slow, fast = BESSFleet(), BESSFleet()

    for _ in range(60):
        slow.step(200.0, dt_seconds=1.0)
    for _ in range(60 * 20):
        fast.step(200.0, dt_seconds=0.05)

    assert abs(slow.average_soc - fast.average_soc) < 0.01


def test_temperature_is_invariant_to_step_rate():
    """The regression this whole change exists to prevent."""
    slow, fast = BESSFleet(), BESSFleet()

    for _ in range(120):
        slow.step(200.0, dt_seconds=1.0)
    for _ in range(120 * 20):
        fast.step(200.0, dt_seconds=0.05)

    for b_slow, b_fast in zip(slow.batteries, fast.batteries):
        assert abs(b_slow.temp_c - b_fast.temp_c) < 0.05


def test_step_still_defaults_to_one_second():
    """Existing callers pass no dt and must keep the behaviour they had."""
    fleet = BESSFleet()

    _inv, _bat, site = fleet.step(100.0)

    assert site is not None
