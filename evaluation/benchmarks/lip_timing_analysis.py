"""Where does lip-sync error come from: alignment, look-ahead, or the model?

All on the stored MEAD feature packs of the validation actors (never the test actors), CPU.

1. Feature-to-mouth alignment. A ridge regression predicts the mouth-opening signal of
   frame t from the speech feature of frame t + d, for d = -6 .. +10 frames, fitted on half
   of the clips and scored on the other half. The d with the best score is where the audio
   that explains the mouth actually is. A model that may only look ``lookahead`` frames
   ahead cannot use audio beyond that.
   A second probe uses a window of features [t - 4, t + d] to show how much the future
   context adds as d grows.
2. Model timing. For each checkpoint, the lag between predicted and real mouth opening
   (cross-correlation per clip, +-8 frames), correlation at zero lag, and how often the
   prediction closes the mouth where the real mouth closes.

"Mouth opening" is the first principal component of the real lip-keypoint motion
(computed on the analysis half), which in MEAD is the jaw/lip opening axis.

    python -m evaluation.benchmarks.lip_timing_analysis --packs outputs/local/packed \
        --checkpoints outputs/local/reg_model.pt outputs/local/it_ccc_la2.pt
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import torch

from emostream.constants import EXP_DIM, LIP_KEYPOINTS
from emostream.training.data import ClipSet

VAL_ACTORS = ("M005", "M024", "W026", "W035")


def load_val(packs: str, max_per_actor: int) -> ClipSet:
    rows, store = [], {}
    for actor in VAL_ACTORS:
        z = np.load(os.path.join(packs, f"{actor}.npz"))
        arr = {k: z[k] for k in ("exp", "pose", "t", "scale", "hubert")}
        ends = np.cumsum(z["lengths"])
        items = list(zip(z["clip_ids"].tolist(), z["emotions"].tolist(), z["levels"].tolist(), ends - z["lengths"], ends))
        neutral = [it for it in items if it[1] == "neutral"]
        other = [it for it in items if it[1] != "neutral"]
        pick = neutral + other[:: max(1, len(other) // max(1, max_per_actor - len(neutral)))]
        for cid, emo, lv, s, e in pick[:max_per_actor] if max_per_actor else pick:
            store[cid] = (arr, int(s), int(e))
            rows.append({"clip_id": cid, "actor": actor, "emotion": emo, "level": int(lv), "split": "val", "features": cid})

    def loader(cid):
        arr, s, e = store[cid]
        return {k: v[s:e] for k, v in arr.items()}

    return ClipSet(rows, loader=loader, lookahead=0)


def lip_columns():
    m = np.zeros((21, 3), bool)
    m[list(LIP_KEYPOINTS)] = True
    return np.where(m.reshape(-1))[0]


def opening_axis(clips, cols):
    y = np.concatenate([c["y_art"][:, cols] for c in clips], 0)
    y = y - y.mean(0)
    _, _, vt = np.linalg.svd(y[:: 3], full_matrices=False)
    ax = vt[0]
    return ax, y.mean(0) * 0


def ridge(X, Y, lam):
    XtX = X.T @ X
    return np.linalg.solve(XtX + lam * np.eye(len(XtX)), X.T @ Y)


def probe(clips, cols, ax, shifts, window=0, lam=300.0, dim=256, seed=0):
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(clips))
    fit, test = [clips[i] for i in order[: len(order) // 2]], [clips[i] for i in order[len(order) // 2:]]
    # random projection of the 1024-d feature keeps the probe cheap and well conditioned
    P = rng.standard_normal((clips[0]["audio"].shape[1], dim)).astype(np.float32) / np.sqrt(dim)

    def design(cs, d):
        X, Y = [], []
        for c in cs:
            f = c["audio"] @ P
            T = len(f)
            o = (c["y_art"][:, cols] @ ax)
            idx = np.arange(T)
            parts = []
            for w in range(-window, 1):
                j = np.clip(idx + d + w, 0, T - 1)
                parts.append(f[j])
            X.append(np.concatenate(parts, 1))
            Y.append(o)
        X = np.concatenate(X, 0)
        return np.concatenate([X, np.ones((len(X), 1), np.float32)], 1), np.concatenate(Y, 0)

    out = {}
    for d in shifts:
        Xf, Yf = design(fit, d)
        Xt, Yt = design(test, d)
        w = ridge(Xf, Yf, lam)
        p = Xt @ w
        out[d] = float(np.corrcoef(p, Yt)[0, 1])
    return out


def model_timing(path, clips, cols, ax, max_lag=8):
    from emostream.models import BehaviourNet

    net = BehaviourNet.load(torch.load(path, map_location="cpu", weights_only=False)).eval()
    la = int(getattr(net.cfg, "lookahead", 0))
    from emostream.training.data import shift_features

    lags, c0s, cbest, closure_hits, closures = [], [], [], 0, 0
    pred_amp, gt_amp = [], []
    for c in clips:
        x = torch.from_numpy(shift_features(c["audio"], la)[None]).float()
        e = torch.from_numpy(np.repeat(c["emo"][None, None], x.shape[1], 1)).float()
        with torch.no_grad():
            p = net(x, e)[0][0].numpy()
        po = p[:, cols] @ ax
        go = c["y_art"][:, cols] @ ax
        if len(go) < 30 or go.std() < 1e-6 or po.std() < 1e-8:
            continue
        pz, gz = (po - po.mean()) / po.std(), (go - go.mean()) / go.std()
        best, bc = 0, -2
        for k in range(-max_lag, max_lag + 1):
            a, b = (pz[k:], gz[: len(gz) - k]) if k >= 0 else (pz[:k], gz[-k:])
            cc = float(np.mean(a * b))
            if k == 0:
                c0s.append(cc)
            if cc > bc:
                best, bc = k, cc
        lags.append(best)
        cbest.append(bc)
        pred_amp.append(po.std())
        gt_amp.append(go.std())
        # closures: real local minima in the lowest 15 % of this clip's opening range
        lo = np.percentile(go, 15)
        for t in range(2, len(go) - 2):
            if go[t] <= lo and go[t] == go[t - 2: t + 3].min():
                closures += 1
                window = po[max(0, t - 1): t + 2].min()
                if window <= np.percentile(po, 30):
                    closure_hits += 1
    lags = np.asarray(lags)
    return {"checkpoint": os.path.basename(path), "lookahead": la, "clips": int(len(lags)),
            "lag_frames_median": float(np.median(lags)), "lag_frames_mean": round(float(lags.mean()), 2),
            "lag_histogram": {int(k): int((lags == k).sum()) for k in range(-max_lag, max_lag + 1) if (lags == k).any()},
            "corr_at_zero_lag": round(float(np.mean(c0s)), 3), "corr_at_best_lag": round(float(np.mean(cbest)), 3),
            "closure_recall": round(closure_hits / max(closures, 1), 3), "closures": closures,
            "opening_amplitude_ratio": round(float(np.mean(pred_amp) / np.mean(gt_amp)), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs", required=True)
    ap.add_argument("--checkpoints", nargs="*", default=[])
    ap.add_argument("--max-per-actor", type=int, default=150)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    clips = load_val(a.packs, a.max_per_actor).clips
    cols = lip_columns()
    ax, _ = opening_axis(clips, cols)
    res = {"clips": len(clips), "frames": int(sum(len(c["y"]) for c in clips))}
    print(json.dumps(res), flush=True)
    res["probe_single_frame"] = probe(clips, cols, ax, list(range(-6, 11)))
    print("single-frame probe (feature of frame t+d -> opening at t):",
          json.dumps({k: round(v, 3) for k, v in res["probe_single_frame"].items()}), flush=True)
    res["probe_window"] = probe(clips, cols, ax, [0, 1, 2, 3, 4, 6, 8], window=4)
    print("window probe (features t-4 .. t+d):",
          json.dumps({k: round(v, 3) for k, v in res["probe_window"].items()}), flush=True)
    res["models"] = []
    for ck in a.checkpoints:
        r = model_timing(ck, clips, cols, ax)
        res["models"].append(r)
        print(json.dumps(r), flush=True)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
