"""Audio-video offset of a session recording made against the timing stand-in.

``fake_server --video ...`` paints the loudness of each frame's own audio as a white block
in the top-right corner. In a recording, the block's brightness over time and the loudness
of the sound track must therefore coincide; the lag at which they correlate best is the
audio-video offset a viewer of that recording gets.

    python -m evaluation.benchmarks.recording_av_offset session.webm
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

STEP_MS = 10


def measure(path: str) -> dict:
    import cv2
    import soundfile as sf

    work = Path(tempfile.mkdtemp(prefix="avoff_"))
    wav = work / "a.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    audio, sr = sf.read(str(wav), dtype="float32")
    # picture: brightness of the block, with each frame's presentation time
    probe = subprocess.run(["ffprobe", "-loglevel", "error", "-select_streams", "v:0", "-show_entries",
                            "frame=pts_time", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    times = [float(x.split(",")[0]) for x in probe.stdout.split() if x.strip() and x.split(",")[0] != "N/A"]
    cap = cv2.VideoCapture(path)
    bright = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        n = f.shape[1]
        bright.append(float(f[12:68, n - 68:n - 12].mean()))
    cap.release()
    m = min(len(times), len(bright))
    times, bright = np.asarray(times[:m]), np.asarray(bright[:m])
    grid = np.arange(0, min(times[-1], len(audio) / sr), STEP_MS / 1000)
    # the block shown at time t is that of the last frame presented at or before t
    idx = np.clip(np.searchsorted(times, grid, side="right") - 1, 0, m - 1)
    v = bright[idx]
    hop = int(sr * STEP_MS / 1000)
    win = int(sr * 0.04)
    a = np.asarray([np.sqrt((audio[i * hop:i * hop + win] ** 2).mean()) if i * hop + win <= len(audio) else 0.0
                    for i in range(len(grid))])
    v, a = v - v.mean(), a - a.mean()
    best, best_c, curve = 0, -2.0, {}
    for lag in range(-150, 151):                      # +-1.5 s; lag > 0: picture later than sound
        if lag >= 0:
            x, y = v[lag:], a[:len(a) - lag]
        else:
            x, y = v[:lag], a[-lag:]
        c = float(np.corrcoef(x, y)[0, 1]) if len(x) > 50 else -2.0
        curve[lag * STEP_MS] = c
        if c > best_c:
            best, best_c = lag, c
    return {"file": path, "seconds": round(float(grid[-1]), 1), "video_frames": int(m),
            "recorded_fps": round(m / max(times[-1] - times[0], 1e-6), 2),
            "picture_later_than_sound_ms": best * STEP_MS, "correlation_at_best": round(best_c, 3),
            "correlation_at_zero": round(curve[0], 3)}


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(json.dumps(measure(f), indent=1))
