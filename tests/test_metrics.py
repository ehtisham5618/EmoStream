import numpy as np
import pytest

from emostream.metrics.motion import boundary_jerk, derivatives, freeze_ratio, jerk_reduction, smoothness


def test_derivatives_of_a_quadratic():
    t = np.arange(50) / 25.0
    m = (3 * t**2)[:, None]            # velocity 6t, acceleration 6, jerk 0
    v, a, j = derivatives(m)
    assert np.allclose(a, 6.0, atol=1e-6) and np.allclose(j, 0.0, atol=1e-5)
    assert v.shape == (49, 1) and a.shape == (48, 1) and j.shape == (47, 1)


def test_a_step_has_far_more_boundary_jerk_than_a_ramp():
    step = np.concatenate([np.zeros(50), np.ones(50)])[:, None]
    ramp = np.concatenate([np.zeros(45), np.linspace(0, 1, 10), np.ones(45)])[:, None]
    assert boundary_jerk(step, 50) > 5 * boundary_jerk(ramp, 50)
    assert jerk_reduction(ramp, step, 50) > 0.8
    assert jerk_reduction(step, step, 50) == pytest.approx(0.0)
    assert boundary_jerk(step, 10) == 0.0          # nothing happens away from the boundary


def test_smoothness_and_freeze_ratio():
    still = np.zeros((40, 3))
    assert smoothness(still) == {"velocity": 0.0, "acceleration": 0.0, "jerk": 0.0}
    assert freeze_ratio(still) == 1.0
    moving = np.cumsum(np.ones((40, 3)), axis=0)
    assert freeze_ratio(moving) == 0.0 and smoothness(moving)["velocity"] == pytest.approx(25.0)
