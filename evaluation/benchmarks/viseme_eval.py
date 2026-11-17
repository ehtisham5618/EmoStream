"""Phoneme-level articulation: does each sound get the right mouth shape at the right time?

Inputs (downloaded from the data volume):
  phonemes/<clip>.json      transcript and force-aligned IPA phonemes (modal/apps/phonemes.py)
  <tag>/lm106/<clip>.npy    106 landmarks per frame, for "gt" (the real video) and model tags

Mouth geometry per frame, normalised by the distance between the eye centres:
  gap     inner-lip gap (upper inner lip midpoint to lower inner lip midpoint): ~0 when closed
  open    outer-lip height (includes lip thickness)
  width   mouth-corner distance
  round   open / width (higher = rounder, narrower)

Measures, per model, against the real video of the same clip:
  1. Bilabial closure (/p b m/): real closure = inner gap in the bottom 20 % of the clip's
     range within [onset - 100 ms, offset]. Model closure, same rule. Recall (real closures the
     model also closes), precision (model closures on bilabials that are real), timing error of
     the gap minimum, and false closures on open vowels.
  2. Viseme distinctness: for each phoneme occurrence of a viseme class, the mouth geometry at
     the phoneme centre (z-scored within its clip). A nearest-centroid classifier trained on the
     *real* geometry is applied to each model's geometry: accuracy shows whether the model's
     mouth shapes carry the same class information. Chance = 1 / number of classes.
  3. Per-class shape error: mean |model - real| of z-scored gap, width and round per class.
  4. Timing: lag of maximum cross-correlation between model and real inner-lip gap.

    python -m evaluation.benchmarks.viseme_eval --root outputs/compare/phoneme --tags slot_s4 ev_wl_base ev_reg
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict

import numpy as np

FPS = 25.0
# insightface 2d106 mouth indices (verified on a labelled frame, see the report)
UPPER_INNER, LOWER_INNER = (71,), (60,)          # placeholders, set by --upper/--lower
LEFT_CORNER, RIGHT_CORNER = 52, 61

VISEMES = {
    "bilabial (p b m)": {"p", "b", "m"},
    "labiodental (f v)": {"f", "v"},
    "dental (th)": {"θ", "ð"},
    "rounded (oo w oh)": {"u", "uː", "ʊ", "w", "oʊ", "o", "ɔ", "ɔː", "ɔɪ"},
    "open (ah aa)": {"ɑ", "ɑː", "æ", "a", "aɪ", "aʊ", "ʌ"},
    "spread (ee)": {"i", "iː", "ɪ", "eɪ", "e"},
    "postalveolar (sh ch j)": {"ʃ", "ʒ", "tʃ", "dʒ"},
}


def geometry(lm: np.ndarray, upper, lower) -> dict:
    eyes = np.linalg.norm(lm[:, 33:43].mean(1) - lm[:, 87:97].mean(1), axis=1) + 1e-6
    up = lm[:, list(upper)].mean(1)
    lo = lm[:, list(lower)].mean(1)
    mouth = lm[:, 52:72]
    open_ = (mouth[..., 1].max(1) - mouth[..., 1].min(1)) / eyes
    width = np.linalg.norm(lm[:, LEFT_CORNER] - lm[:, RIGHT_CORNER], axis=1) / eyes
    gap = np.clip((lo[:, 1] - up[:, 1]) / eyes, 0, None)
    centre = mouth.mean(1, keepdims=True)
    shape = ((mouth - centre) / eyes[:, None, None]).reshape(len(lm), -1)     # 20-point mouth shape, 40 values
    return {"gap": gap, "open": open_, "width": width, "round": open_ / (width + 1e-6), "shape": shape}


def zs(x):
    x = np.asarray(x, float)
    s = np.nanstd(x)
    return (x - np.nanmean(x)) / (s if s > 1e-9 else 1.0)


def viseme_of(p: str):
    for name, ps in VISEMES.items():
        if p in ps:
            return name
    return None


def load(root, tag, clip, upper, lower):
    path = os.path.join(root, tag, "lm106", clip + ".npy")
    if not os.path.exists(path):
        return None
    lm = np.load(path)
    if np.isnan(lm).all():
        return None
    return geometry(lm, upper, lower)


def closure_frames(gap: np.ndarray, frac: float = 0.2) -> np.ndarray:
    lo, hi = np.nanpercentile(gap, 2), np.nanpercentile(gap, 98)
    return gap <= lo + frac * (hi - lo)


def evaluate(root: str, tags: list[str], upper, lower, min_phone_score: float) -> dict:
    clips = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(root, "phonemes", "*.json")))
    res = {"clips": 0, "phonemes_used": 0, "tags": {}}
    per_tag = {t: defaultdict(list) for t in tags}
    gt_samples, tag_samples = [], {t: [] for t in tags}
    for clip in clips:
        ph = json.load(open(os.path.join(root, "phonemes", clip + ".json"), encoding="utf-8"))
        if not ph.get("phones") or ph.get("mean_phone_score", 0) < min_phone_score:
            continue
        g = load(root, "gt", clip, upper, lower)
        if g is None:
            continue
        ms = {t: load(root, t, clip, upper, lower) for t in tags}
        if any(m is None for m in ms.values()):
            continue
        res["clips"] += 1
        n = min([len(g["gap"])] + [len(m["gap"]) for m in ms.values()])
        g = {k: v[:n] for k, v in g.items()}
        ms = {t: {k: v[:n] for k, v in m.items()} for t, m in ms.items()}
        zsh = lambda a: (a - np.nanmean(a, 0)) / (np.nanstd(a) + 1e-9)          # per clip: remove the face's own mean shape
        gz = {k: (zsh(v) if k == "shape" else zs(v)) for k, v in g.items()}
        mz = {t: {k: (zsh(v) if k == "shape" else zs(v)) for k, v in m.items()} for t, m in ms.items()}
        g_closed = closure_frames(g["gap"])
        m_closed = {t: closure_frames(m["gap"]) for t, m in ms.items()}
        for p in ph["phones"]:
            v = viseme_of(p["p"])
            if v is None:
                continue
            a, b = int((p["start"] - 0.1) * FPS), int(np.ceil(p["end"] * FPS))
            c = int(round((p["start"] + p["end"]) / 2 * FPS))
            if a < 0 or b >= n or c >= n:
                continue
            res["phonemes_used"] += 1
            feat = lambda d: list(d["shape"][max(a + 2, c - 1):c + 2].mean(0))      # mouth shape around the phoneme centre
            gt_samples.append((v, feat(gz)))
            for t in tags:
                tag_samples[t].append((v, feat(mz[t])))
                for k in ("gap", "width", "round"):
                    per_tag[t][f"err_{k}|{v}"].append(abs(mz[t][k][c] - gz[k][c]))
                if v.startswith("bilabial"):
                    gclose = bool(g_closed[a:b + 1].any())
                    mclose = bool(m_closed[t][a:b + 1].any())
                    # strict, absolute: inner lips within 3 % of the eye distance
                    per_tag[t]["bil_real_closed_abs"].append(bool((g["gap"][a:b + 1] < 0.03).any()))
                    per_tag[t]["bil_model_closed_abs"].append(bool((ms[t]["gap"][a:b + 1] < 0.03).any()))
                    per_tag[t]["bil_real_closed"].append(gclose)
                    per_tag[t]["bil_model_closed"].append(mclose)
                    if gclose and mclose:
                        per_tag[t]["bil_timing_ms"].append(
                            (int(np.argmin(ms[t]["gap"][a:b + 1])) - int(np.argmin(g["gap"][a:b + 1]))) * 40)
                    per_tag[t]["bil_min_gap_model"].append(float(np.min(ms[t]["gap"][a:b + 1])))
                    per_tag[t]["bil_min_gap_real"].append(float(np.min(g["gap"][a:b + 1])))
                if v.startswith("open"):
                    per_tag[t]["open_vowel_false_closure"].append(bool(m_closed[t][c]) and not bool(g_closed[c]))
        # timing of the whole inner-lip trajectory
        for t in tags:
            best, bc = 0, -2
            x, y = zs(g["gap"]), zs(ms[t]["gap"])
            for k in range(-6, 7):
                aa, bb = (y[k:], x[:n - k]) if k >= 0 else (y[:k], x[-k:])
                cc = float(np.nanmean(aa * bb))
                if cc > bc:
                    best, bc = k, cc
            per_tag[t]["lag_frames"].append(best)
            per_tag[t]["gap_corr0"].append(float(np.nanmean(x * y)))
    # viseme distinctness: nearest centroid trained on real geometry
    classes = sorted({v for v, _ in gt_samples})
    cent = {v: np.nanmean([f for vv, f in gt_samples if vv == v], 0) for v in classes}

    def accuracy(samples):
        ok = []
        for v, f in samples:
            if np.isnan(f).any():
                continue
            pred = min(classes, key=lambda u: np.linalg.norm(np.asarray(f) - cent[u]))
            ok.append(pred == v)
        return float(np.mean(ok)) if ok else float("nan")

    # leave-one-out on real data so the real score is not inflated by its own centroids
    def loo_accuracy(samples):
        ok = []
        arr = [(v, np.asarray(f)) for v, f in samples if not np.isnan(f).any()]
        for i, (v, f) in enumerate(arr):
            c2 = {u: np.mean([g for j, (vv, g) in enumerate(arr) if vv == u and j != i], 0) for u in classes}
            pred = min(classes, key=lambda u: np.linalg.norm(f - c2[u]))
            ok.append(pred == v)
        return float(np.mean(ok))

    res["viseme_classes"] = {v: sum(1 for vv, _ in gt_samples if vv == v) for v in classes}
    res["chance"] = round(1 / len(classes), 3) if classes else None
    res["real_video_distinctness"] = round(loo_accuracy(gt_samples), 3)
    for t in tags:
        d = per_tag[t]
        rc, mc = np.array(d["bil_real_closed"]), np.array(d["bil_model_closed"])
        ra, ma = np.array(d["bil_real_closed_abs"]), np.array(d["bil_model_closed_abs"])
        res["tags"][t] = {
            "viseme_distinctness": round(accuracy(tag_samples[t]), 3),
            "bilabial": {"n": int(len(rc)), "real_closed": int(rc.sum()),
                         "recall": round(float((rc & mc).sum() / max(rc.sum(), 1)), 3),
                         "model_closed_on_bilabials": int(mc.sum()),
                         "precision": round(float((rc & mc).sum() / max(mc.sum(), 1)), 3),
                         "timing_ms_median": float(np.median(d["bil_timing_ms"])) if d["bil_timing_ms"] else None,
                         "timing_ms_mean_abs": round(float(np.mean(np.abs(d["bil_timing_ms"]))), 1) if d["bil_timing_ms"] else None,
                         "min_gap_model_mean": round(float(np.mean(d["bil_min_gap_model"])), 4),
                         "min_gap_real_mean": round(float(np.mean(d["bil_min_gap_real"])), 4),
                         "strict_real_closed": int(ra.sum()), "strict_model_closed": int(ma.sum()),
                         "strict_recall": round(float((ra & ma).sum() / max(ra.sum(), 1)), 3),
                         "strict_precision": round(float((ra & ma).sum() / max(ma.sum(), 1)), 3)},
            "open_vowel_false_closure_rate": round(float(np.mean(d["open_vowel_false_closure"])), 3)
            if d["open_vowel_false_closure"] else None,
            "inner_gap_corr_lag0": round(float(np.mean(d["gap_corr0"])), 3),
            "inner_gap_best_lag_frames_median": float(np.median(d["lag_frames"])),
            "shape_error_by_class": {v: {k: round(float(np.mean(d[f"err_{k}|{v}"])), 3) for k in ("gap", "width", "round")
                                         if d[f"err_{k}|{v}"]} for v in classes},
        }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--upper", default="71", help="comma-separated landmark indices of the upper inner lip midpoint")
    ap.add_argument("--lower", default="60", help="comma-separated landmark indices of the lower inner lip midpoint")
    ap.add_argument("--min-phone-score", type=float, default=0.0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    up = tuple(int(x) for x in a.upper.split(","))
    lo = tuple(int(x) for x in a.lower.split(","))
    res = evaluate(a.root, ["gt"] + a.tags if False else a.tags, up, lo, a.min_phone_score)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
