"""Phoneme-level check of a rendering of the user's own recording (no real video exists).

For each viseme class, the avatar's mouth around the phoneme centre is summarised, and the
classes are compared with each other: a mouth that articulates closes on /p b m/, opens most
on open vowels, is narrowest on rounded vowels and widest on spread vowels. Generic motion
gives similar values for every class.

Reported per class (inner-lip gap and width normalised by eye distance, z-scored over the
recording's speech frames): mean gap, mean width; and for /p b m/ the share with full
closure (gap < 0.03) within [onset - 100 ms, offset].

    python -m evaluation.benchmarks.user_recording_eval outputs/compare/phoneme/user_wl_base.json ...
"""
from __future__ import annotations

import json
import sys

import numpy as np

from evaluation.benchmarks.viseme_eval import VISEMES, viseme_of

UP, LO = [62, 66, 70], [60, 54, 57]


def summarise(path: str) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    t = np.asarray(d["times"])
    L = np.asarray(d["landmarks"], dtype=np.float32)
    eyes = np.linalg.norm(L[:, 33:43].mean(1) - L[:, 87:97].mean(1), axis=1)
    gap = (L[:, LO, 1].mean(1) - L[:, UP, 1].mean(1)) / eyes
    width = np.linalg.norm(L[:, 52] - L[:, 61], axis=1) / eyes
    phones = [p for s in d["alignment"]["segments"] for p in s["phones"]]
    speech = np.zeros(len(t), bool)
    for p in phones:
        speech |= (t >= p["start"]) & (t <= p["end"])
    gz = (gap - np.nanmean(gap[speech])) / (np.nanstd(gap[speech]) + 1e-9)
    wz = (width - np.nanmean(width[speech])) / (np.nanstd(width[speech]) + 1e-9)
    by = {v: {"gap": [], "width": [], "closed": []} for v in VISEMES}
    for p in phones:
        v = viseme_of(p["p"])
        if v is None:
            continue
        c = (p["start"] + p["end"]) / 2
        win = (t >= c - 0.04) & (t <= c + 0.04)
        if win.any():
            by[v].setdefault("gap_abs", []).append(float(np.nanmean(gap[win])))
            by[v]["gap"].append(float(np.nanmean(gz[win])))
            by[v]["width"].append(float(np.nanmean(wz[win])))
        if v.startswith("bilabial"):
            w2 = (t >= p["start"] - 0.1) & (t <= p["end"] + 0.02)
            by[v]["closed"].append(bool(w2.any() and np.nanmin(gap[w2]) < 0.03))
    out = {"transcript": " | ".join(s["transcript"] for s in d["alignment"]["segments"]),
           "phone_score": [s.get("mean_phone_score") for s in d["alignment"]["segments"]], "classes": {}}
    for v, x in by.items():
        if x["gap"]:
            out["classes"][v] = {"n": len(x["gap"]), "gap_abs": round(float(np.mean(x["gap_abs"])), 3),
                                 "gap_z": round(float(np.mean(x["gap"])), 2),
                                 "width_z": round(float(np.mean(x["width"])), 2)}
            if x["closed"]:
                out["classes"][v]["full_closure_rate"] = round(float(np.mean(x["closed"])), 2)
    g = [out["classes"][v]["gap_z"] for v in out["classes"]]
    w = [out["classes"][v]["width_z"] for v in out["classes"]]
    out["spread_between_classes"] = {"gap": round(float(np.std(g)), 3), "width": round(float(np.std(w)), 3)}
    return out


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f)
        print(json.dumps(summarise(f), indent=1, ensure_ascii=False))
