"""Motion-space smoothness metrics, computed on per-frame motion vectors at 25 FPS."""
from __future__ import annotations

import numpy as np

from ..constants import FPS


def derivatives(motion: np.ndarray, fps: int = FPS):
    """Velocity, acceleration and jerk by finite differences, in units per second^n.
    motion: (T, D)."""
    m = np.asarray(motion, dtype=np.float64)
    v = np.diff(m, axis=0) * fps
    a = np.diff(v, axis=0) * fps
    j = np.diff(a, axis=0) * fps
    return v, a, j


def smoothness(motion: np.ndarray, fps: int = FPS) -> dict:
    """Mean absolute velocity, acceleration and jerk over a sequence."""
    v, a, j = derivatives(motion, fps)
    return {"velocity": float(np.abs(v).mean()) if len(v) else 0.0,
            "acceleration": float(np.abs(a).mean()) if len(a) else 0.0,
            "jerk": float(np.abs(j).mean()) if len(j) else 0.0}


def boundary_jerk(motion: np.ndarray, boundary: int, half_window: int = 5, fps: int = FPS) -> float:
    """Mean absolute jerk in the frames around a boundary (an emotion change or a chunk edge).

    Jerk sample i is computed from frames i..i+3, so the window covers every jerk
    value that involves a frame within ``half_window`` of the boundary.
    """
    _, _, j = derivatives(motion, fps)
    lo = max(0, boundary - half_window - 3)
    hi = min(len(j), boundary + half_window)
    if hi <= lo:
        return 0.0
    return float(np.abs(j[lo:hi]).mean())


def jerk_reduction(smooth: np.ndarray, abrupt: np.ndarray, boundary: int, half_window: int = 5) -> float:
    """Relative reduction of boundary jerk: 0.2 means 20 % lower than the abrupt version."""
    b = boundary_jerk(abrupt, boundary, half_window)
    if b <= 0:
        return 0.0
    return float(1.0 - boundary_jerk(smooth, boundary, half_window) / b)


def freeze_ratio(motion: np.ndarray, eps: float = 1e-6) -> float:
    """Fraction of frames identical to the previous one (frozen output)."""
    m = np.asarray(motion)
    if len(m) < 2:
        return 0.0
    return float((np.abs(np.diff(m, axis=0)).max(axis=1) < eps).mean())
