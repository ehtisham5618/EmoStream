"""Checks that MEAD audio files (.m4a, from audio.tar) pair with the motion clips by number.

The motion packs were built from the videos, with the audio taken from each video's own
track. For some actors the video files are numbered differently from the audio files, so
"same emotion, level and number" may name a different sentence. A correct pair has the
.m4a about 40 ms shorter than the video (checked on M005: identical content, 0 ms offset).

For every pack clip this reports: audio file present, and |video duration - audio duration|.
Pairs within ``--tolerance-ms`` (default 120) count as consistent.

    python -m evaluation.benchmarks.mead_audio_pairing --packs outputs/local/packed --audio outputs/local/mead_tar
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess

import numpy as np


def duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:      # unreadable file (seen once: M041 sad level 2, 013)
        return float("nan")


def check(actor: str, packs: str, audio_root: str, tol_ms: float) -> dict:
    z = np.load(os.path.join(packs, f"{actor}.npz"))
    rows = []
    for cid, n in zip(z["clip_ids"].tolist(), z["lengths"].tolist()):
        _, emo, lv, num = cid.split("_")
        p = os.path.join(audio_root, actor, "audio", emo, f"level_{lv[1:]}", f"{num}.m4a")
        if not os.path.exists(p):
            rows.append((cid, None))
            continue
        d = duration(p)
        rows.append((cid, None if d != d else (n * 0.04 - d) * 1000))
    present = [d for _, d in rows if d is not None]
    ok = [d for d in present if abs(d) <= tol_ms]
    return {"actor": actor, "clips": len(rows), "audio_present": len(present), "duration_consistent": len(ok),
            "median_video_minus_audio_ms": round(float(np.median(present)), 1) if present else None,
            "consistent_ids": [c for c, d in rows if d is not None and abs(d) <= tol_ms]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--tolerance-ms", type=float, default=120.0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    actors = sorted(f[:-4] for f in os.listdir(a.packs) if f.endswith(".npz"))
    res = []
    for actor in actors:
        if not os.path.isdir(os.path.join(a.audio, actor)):
            continue
        r = check(actor, a.packs, a.audio, a.tolerance_ms)
        res.append(r)
        print(json.dumps({k: v for k, v in r.items() if k != "consistent_ids"}), flush=True)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
