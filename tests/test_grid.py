"""Grid frequency model.

The sign convention is the whole point of this file. A droop response built on
a backwards sign is a controller that confidently amplifies every disturbance
it sees, and it looks completely plausible until the grid asks it for help.
Pin the direction here, before any controller exists to inherit the mistake.
"""

import random

from src.simulator.grid import GridModel, GridProfile


def quiet_profile(**overrides) -> GridProfile:
    """A profile with ambient load noise disabled, so tests are deterministic."""
    base = {"load_noise_pu": 0.0}
    base.update(overrides)
    return GridProfile(**base)


def run(grid: GridModel, plant_p_kw: float, seconds: float, dt: float = 0.05) -> float:
    for _ in range(int(seconds / dt)):
        grid.step(plant_p_kw, dt)
    return grid.frequency_hz


def test_balanced_system_holds_nominal():
    grid = GridModel(quiet_profile())

    assert run(grid, plant_p_kw=0.0, seconds=30) == 50.0
    assert grid.rocof_hz_s == 0.0


def test_generation_deficit_lowers_frequency():
    grid = GridModel(quiet_profile())
    grid.set_disturbance(-50.0)  # 50 kW of generation lost

    assert run(grid, plant_p_kw=0.0, seconds=10) < 50.0
    assert grid.rocof_hz_s < 0.0


def test_charging_lowers_frequency():
    """Charging is a LOAD. It must push frequency down, not up."""
    grid = GridModel(quiet_profile())

    assert run(grid, plant_p_kw=+250.0, seconds=10) < 50.0


def test_discharging_raises_frequency():
    """Discharging is GENERATION. It must push frequency up."""
    grid = GridModel(quiet_profile())

    assert run(grid, plant_p_kw=-250.0, seconds=10) > 50.0


def test_plant_can_arrest_a_deficit():
    """The reason the model exists: the plant's response must change the outcome."""
    unhelped = GridModel(quiet_profile())
    unhelped.set_disturbance(-250.0)
    f_unhelped = run(unhelped, plant_p_kw=0.0, seconds=20)

    helped = GridModel(quiet_profile())
    helped.set_disturbance(-250.0)
    f_helped = run(helped, plant_p_kw=-250.0, seconds=20)  # discharge to fill the gap

    assert f_helped > f_unhelped
    assert abs(f_helped - 50.0) < 0.01  # deficit exactly cancelled


def test_initial_rocof_is_set_by_inertia():
    """First-instant RoCoF = ΔP_pu · f_nom / 2H, independent of damping."""
    grid = GridModel(quiet_profile(system_base_kw=5_000.0, inertia_h_s=4.0))
    grid.set_disturbance(-500.0)  # -0.1 pu

    grid.step(plant_p_kw=0.0, dt_seconds=0.05)

    assert abs(grid.rocof_hz_s - (-0.1 * 50.0 / 8.0)) < 1e-9


def test_steady_state_offset_is_set_by_damping():
    """At equilibrium the imbalance is absorbed by load damping: Δf = ΔP_pu·f_nom/D."""
    grid = GridModel(quiet_profile(damping_d=1.5))
    grid.set_disturbance(-50.0)  # -0.01 pu

    f = run(grid, plant_p_kw=0.0, seconds=120)

    assert abs(f - (50.0 + (-0.01 * 50.0 / 1.5))) < 0.005


def test_system_size_decides_whether_the_plant_matters():
    """The stiffness knob: the same plant barely dents a large system."""
    weak = GridModel(quiet_profile(system_base_kw=5_000.0))
    stiff = GridModel(quiet_profile(system_base_kw=500_000.0))

    run(weak, plant_p_kw=250.0, seconds=20)
    run(stiff, plant_p_kw=250.0, seconds=20)

    assert abs(weak.delta_f_hz) > 50 * abs(stiff.delta_f_hz)


def test_ambient_noise_keeps_frequency_moving_but_close():
    """Real frequency wanders. A deadband needs something to ignore."""
    grid = GridModel(GridProfile(), rng=random.Random(7))

    samples = [grid.step(0.0, 0.05) for _ in range(4000)]

    assert len(set(samples)) > 100          # it genuinely moves
    assert max(abs(s - 50.0) for s in samples) < 0.2   # but stays plausible
