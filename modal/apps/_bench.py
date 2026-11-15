"""Shared measurement helpers for the proof-of-concept Modal apps.

Copied into each image as /root/_bench.py (see ``with_bench``). Uses only the
standard library plus the ``nvidia-smi`` and ``ffprobe`` binaries.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time


class SmiMeter:
    """Samples whole-device GPU memory with nvidia-smi (framework independent)."""

    def __init__(self, interval: float = 0.25):
        self.peak_mib = 0
        self.baseline_mib = self._read()[0]
        self.name = self._read()[1]
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._t.start()

    @staticmethod
    def _read():
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,name", "--format=csv,noheader,nounits"],
            capture_output=True, text=True,
        ).stdout.strip().splitlines()[0]
        used, name = [x.strip() for x in out.split(",", 1)]
        return int(used), name

    def _loop(self, interval):
        while not self._stop.is_set():
            try:
                self.peak_mib = max(self.peak_mib, self._read()[0])
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(interval)

    def stop(self) -> float:
        self._stop.set()
        self._t.join()
        return round(self.peak_mib / 1024, 3)


def probe_video(path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
         "stream=nb_read_frames,width,height,r_frame_rate", "-of", "json", path],
        capture_output=True, text=True,
    )
    v = json.loads(r.stdout)["streams"][0]
    num, den = v["r_frame_rate"].split("/")
    return {"frames": int(v["nb_read_frames"]), "width": v["width"], "height": v["height"],
            "frame_rate": round(float(num) / float(den), 3)}


def audio_seconds(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def run_cli(cmd: list[str], cwd: str, env: dict | None = None, log_tail: int = 6000) -> dict:
    """Runs a model's own CLI as a subprocess and measures wall time and peak GPU memory.

    The wall time includes process start-up and model loading; callers add
    stage-level timings when the tool reports them.
    """
    import os

    meter = SmiMeter()
    t = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    wall = time.perf_counter() - t
    peak = meter.stop()
    log = (p.stdout or "") + "\n--- stderr ---\n" + (p.stderr or "")
    return {"returncode": p.returncode, "cli_wall_s": round(wall, 2), "device_peak_used_gib": peak,
            "gpu": meter.name, "log_tail": log[-log_tail:]}


def summarize(model: str, cli: dict, out_path: str | None, audio_path: str, extra: dict | None = None) -> dict:
    res = {"model": model, **{k: v for k, v in cli.items() if k != "log_tail"}}
    dur = audio_seconds(audio_path)
    res["audio_s"] = round(dur, 3)
    if out_path and cli["returncode"] == 0:
        v = probe_video(out_path)
        res.update(v)
        res["fps_cli_end_to_end"] = round(v["frames"] / cli["cli_wall_s"], 2)
        res["realtime_factor_cli"] = round(cli["cli_wall_s"] / dur, 2)
        res["output"] = out_path
    res.update(extra or {})
    res["log_tail"] = cli["log_tail"]
    return res
