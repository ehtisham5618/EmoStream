"""Timing and latency statistics for the streaming engine."""
from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager


def percentile(values, q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]. Returns nan for an empty list."""
    xs = sorted(values)
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))


class StageTimer:
    """Accumulates wall time per named stage."""

    def __init__(self):
        self.total = defaultdict(float)
        self.count = defaultdict(int)

    @contextmanager
    def time(self, name: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.total[name] += time.perf_counter() - t
            self.count[name] += 1

    def summary(self, n_frames: int | None = None) -> dict:
        out = {}
        for k in self.total:
            row = {"total_s": round(self.total[k], 4), "calls": self.count[k],
                   "ms_per_call": round(1000 * self.total[k] / max(self.count[k], 1), 3)}
            if n_frames:
                row["ms_per_frame"] = round(1000 * self.total[k] / n_frames, 3)
            out[k] = row
        return out


class LatencyTracker:
    """Audio-to-frame latency: time from the arrival of a frame's last audio sample
    to the moment the rendered frame is handed to the caller."""

    def __init__(self):
        self.latencies_ms: list[float] = []
        self.emit_times: list[float] = []

    def record(self, ready_time: float, emit_time: float | None = None) -> float:
        emit_time = time.perf_counter() if emit_time is None else emit_time
        ms = (emit_time - ready_time) * 1000.0
        self.latencies_ms.append(ms)
        self.emit_times.append(emit_time)
        return ms

    def summary(self, skip: int = 0) -> dict:
        xs = self.latencies_ms[skip:]
        if not xs:
            return {"n": 0}
        ts = self.emit_times[skip:]
        span = ts[-1] - ts[0] if len(ts) > 1 else 0.0
        gaps = [1000 * (b - a) for a, b in zip(ts, ts[1:])]
        return {
            "n": len(xs),
            "p50_ms": round(percentile(xs, 50), 1),
            "p95_ms": round(percentile(xs, 95), 1),
            "max_ms": round(max(xs), 1),
            "mean_ms": round(sum(xs) / len(xs), 1),
            "output_fps": round((len(ts) - 1) / span, 2) if span > 0 else None,
            "max_frame_gap_ms": round(max(gaps), 1) if gaps else None,
        }
