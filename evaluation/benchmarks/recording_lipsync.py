"""Speech-to-mouth offset in a recording (session recording, side-by-side clip, export).

Mouth opening is measured from pixels: the face is found once (OpenCV Haar cascade), and
in a fixed region around the mouth the share of dark pixels (the mouth interior) is taken
per frame. That share is correlated with the loudness envelope of the sound track over
time shifts of -1.5 to +2.5 s. The shift with the highest correlation is how much later
the mouth moves than the voice; the correlation at that shift says how well mouth
opening follows speech at all.

This is a proxy: it sees opening, not lip shape, and needs a roughly frontal, still face.
It does not need the model or the ground truth, so it works on any recording.

    python -m evaluation.benchmarks.recording_lipsync session.webm [--panel 2/3]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

import numpy as np

STEP = 0.02  # s, analysis grid


def video_frames(path: str):
    import cv2

    probe = subprocess.run(["ffprobe", "-loglevel", "error", "-select_streams", "v:0", "-show_entries",
                            "frame=pts_time", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    times = [float(x.split(",")[0]) for x in probe.stdout.split() if x.strip() and x.split(",")[0] != "N/A"]
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    n = min(len(times), len(frames))
    if n < len(frames) and not times:  # container without per-frame times: assume constant rate
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        times = list(np.arange(len(frames)) / fps)
        n = len(frames)
    return np.asarray(times[:n]), frames[:n]


def mouth_roi(frames):
    """The mouth is where the picture changes most over time, below the middle of the image
    (eyes blink, but sit in the upper half). A box of 18 % x 9 % of the frame is placed on
    the maximum of the per-pixel temporal standard deviation."""
    import cv2

    sample = frames[:: max(1, len(frames) // 300)]
    g = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) for f in sample])
    sd = g.std(0)
    H, W = sd.shape
    sd[: int(0.5 * H)] = 0
    sd[int(0.92 * H):] = 0                       # watermark strip
    sd[:, : int(0.2 * W)] = 0
    sd[:, int(0.8 * W):] = 0
    w, h = int(0.18 * W), int(0.09 * H)
    box = cv2.blur(sd, (w, h))
    y, x = np.unravel_index(np.argmax(box), box.shape)
    return int(x - w // 2), int(y - h // 2), w, h


def openness(frames, roi):
    x, y, w, h = roi
    vals = []
    ref = None
    for f in frames:
        patch = f[y:y + h, x:x + w].astype(np.float32).mean(2)
        if ref is None:
            ref = np.percentile(patch, 60)
        vals.append(float((patch < 0.45 * ref).mean()))
    return np.asarray(vals)


def audio_envelope(path: str, grid: np.ndarray) -> np.ndarray:
    import soundfile as sf

    tmp = os.path.join(tempfile.mkdtemp(), "a.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", tmp], check=True)
    a, sr = sf.read(tmp, dtype="float32")
    win = int(0.04 * sr)
    env = np.asarray([np.sqrt((a[int(t * sr):int(t * sr) + win] ** 2).mean() + 1e-10) for t in grid])
    return np.log10(env + 1e-4)


def best_lag(v: np.ndarray, a: np.ndarray, lo: float = -1.5, hi: float = 2.5) -> tuple[float, float, float]:
    v = (v - v.mean()) / (v.std() + 1e-9)
    a = (a - a.mean()) / (a.std() + 1e-9)
    best, best_c, zero = 0.0, -2.0, 0.0
    for k in range(int(lo / STEP), int(hi / STEP) + 1):
        if k >= 0:
            x, y = v[k:], a[:len(a) - k]
        else:
            x, y = v[:k], a[-k:]
        if len(x) < 100:
            continue
        c = float(np.mean(x * y))
        if k == 0:
            zero = c
        if c > best_c:
            best, best_c = k * STEP, c
    return best, best_c, zero


def measure(path: str, panel: str | None = None) -> dict:
    times, frames = video_frames(path)
    if panel:  # "i/n": use the i-th of n side-by-side panels (1-based)
        i, n = (int(p) for p in panel.split("/"))
        w = frames[0].shape[1] // n
        frames = [f[:, (i - 1) * w:i * w] for f in frames]
    roi = mouth_roi(frames)
    if os.environ.get("LIPSYNC_ROI_IMAGE"):
        import cv2

        f = frames[len(frames) // 2].copy()
        x, y, w, h = roi
        cv2.rectangle(f, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cv2.imwrite(os.environ["LIPSYNC_ROI_IMAGE"], f)
    v = openness(frames, roi)
    grid = np.arange(times[0], times[-1], STEP)
    vg = v[np.clip(np.searchsorted(times, grid, side="right") - 1, 0, len(v) - 1)]
    a = audio_envelope(path, grid)
    lag, c, c0 = best_lag(vg, a)
    # per 10-second window, to see whether the offset drifts
    wins = []
    for s in np.arange(0, len(grid) - int(10 / STEP), int(5 / STEP)):
        e = s + int(10 / STEP)
        lw, cw, _ = best_lag(vg[s:e], a[s:e], -1.5, 2.5)
        wins.append([round(float(grid[s]), 1), round(lw, 2), round(cw, 2)])
    return {"file": os.path.basename(path), "panel": panel, "seconds": round(float(times[-1] - times[0]), 1),
            "mouth_later_than_voice_s": round(lag, 2), "correlation_at_best": round(c, 3),
            "correlation_at_zero": round(c0, 3), "windows_[start_s,lag_s,corr]": wins}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--panel", default=None)
    a = ap.parse_args()
    for f in a.files:
        print(json.dumps(measure(f, a.panel)))
