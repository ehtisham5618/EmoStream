"""Emotion control measured in motion space on validation actors (CPU, no renderer).

For every combination of *voice* emotion (the emotion acted in the audio clip) and
*selected* emotion (the control input), the behaviour model is run and compared with the
real expression offsets of the same actor:

* ``selected_cos``   cosine between the predicted mean expression offset and the real
                     offset of the selected emotion (1 = same direction)
* ``voice_cos``      cosine with the real offset of the voice's emotion (leakage when the
                     two differ)
* ``nearest``        which real emotion centroid the predicted mean expression is closest
                     to; accuracy against the selected emotion
* ``neutral_leak``   with neutral selected: size of the predicted offset relative to the
                     real offset of the voice's emotion (0 = the voice does not leak)
* ``lip_corr_vs_neutral``  correlation of lip motion with the same audio rendered as
                     neutral (does articulation survive the emotion?)

Intensity: projection of the predicted offset on the real offset direction at
intensities 0, 0.25, 0.5, 0.75 and 1, as a fraction of the real full-intensity offset.

    python -m evaluation.benchmarks.emotion_control_motion --checkpoint outputs/local/it_ccc.pt \
        --packs outputs/local/packed/M005.npz outputs/local/packed/M024.npz ...
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import torch

from emostream.constants import EMOTIONS, EXP_DIM, LIP_KEYPOINTS
from emostream.engine.emotion import one_hot_with_intensity
from emostream.models import BehaviourNet
from emostream.training.data import shift_features, to_delta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--packs", nargs="+", required=True)
    ap.add_argument("--per-cell", type=int, default=8)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    net = BehaviourNet.load(torch.load(args.checkpoint, map_location="cpu", weights_only=False))
    L = int(getattr(net.cfg, "lookahead", 0))
    lip = np.zeros((21, 3), bool)
    lip[list(LIP_KEYPOINTS)] = True
    lip = lip.reshape(-1)

    def predict(feat, emotion, intensity):
        x = torch.from_numpy(shift_features(feat.astype(np.float32), L))[None]
        e = torch.from_numpy(one_hot_with_intensity(emotion, intensity))[None, None].expand(1, x.shape[1], -1)
        with torch.no_grad():
            return net(x, e)[0][0].numpy()[:, :EXP_DIM]

    cell = {(a, b): {"sel": [], "voice": [], "hit": [], "lipc": []} for a in EMOTIONS for b in EMOTIONS}
    leak = {a: [] for a in EMOTIONS[1:]}
    inten = {e: {i: [] for i in (0.0, 0.25, 0.5, 0.75, 1.0)} for e in EMOTIONS[1:]}
    for pack in args.packs:
        z = np.load(pack)
        ends = np.cumsum(z["lengths"])
        starts = ends - z["lengths"]
        emo, lv = z["emotions"], z["levels"]
        mot = np.concatenate([z["exp"], z["pose"], z["t"][:, :2], z["scale"].reshape(-1, 1)], 1).astype(np.float32)
        neutral = [i for i, x in enumerate(emo) if x == "neutral"]
        rest = np.median(np.concatenate([mot[starts[i]:starts[i] + 3] for i in neutral]), 0)

        def clips_of(e):
            idx = [i for i, x in enumerate(emo) if x == e and (e == "neutral" or lv[i] == 3)]
            return idx

        real_mean = {e: np.concatenate([to_delta(mot[starts[i]:ends[i]].copy(), rest)[:, :EXP_DIM]
                                        for i in clips_of(e)]).mean(0) for e in EMOTIONS}
        real_off = {e: real_mean[e] - real_mean["neutral"] for e in EMOTIONS[1:]}

        def cos(u, v):
            return float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12))

        for a in EMOTIONS:                                   # emotion in the voice
            for i in clips_of(a)[8:8 + args.per_cell]:
                feat = z["hubert"][starts[i]:ends[i]]
                base = predict(feat, "neutral", 1.0)
                for b in EMOTIONS:                           # selected emotion
                    p = base if b == "neutral" else predict(feat, b, 1.0)
                    off = p.mean(0) - real_mean["neutral"]
                    c = cell[(a, b)]
                    if b != "neutral":
                        c["sel"].append(cos(off, real_off[b]))
                    if a != "neutral":
                        c["voice"].append(cos(off, real_off[a]))
                    d = {e: np.linalg.norm(p.mean(0) - real_mean[e]) for e in EMOTIONS}
                    c["hit"].append(min(d, key=d.get) == b)
                    pl, bl = p[:, lip], base[:, lip]
                    mv = bl.std(0) > 0.5 * bl.std(0).max()
                    c["lipc"].append(float(np.mean([np.corrcoef(pl[:, j], bl[:, j])[0, 1] for j in np.where(mv)[0]])))
                if a != "neutral":
                    leak[a].append(float(np.linalg.norm(base.mean(0) - real_mean["neutral"]) /
                                         (np.linalg.norm(real_off[a]) + 1e-12)))
            if a == "neutral":
                for i in clips_of("neutral")[8:8 + args.per_cell]:
                    feat = z["hubert"][starts[i]:ends[i]]
                    base = predict(feat, "neutral", 1.0).mean(0)
                    for b in EMOTIONS[1:]:
                        u = real_off[b] / (np.linalg.norm(real_off[b]) + 1e-12)
                        for k in inten[b]:
                            p = predict(feat, b, k).mean(0)
                            inten[b][k].append(float((p - base) @ u / (np.linalg.norm(real_off[b]) + 1e-12)))

    def m(x):
        return round(float(np.mean(x)), 3) if len(x) else None

    res = {"checkpoint": args.checkpoint, "actors": len(args.packs), "per_cell": args.per_cell,
           "matrix": {f"{a}->{b}": {"selected_cos": m(c["sel"]), "voice_cos": m(c["voice"]),
                                    "nearest_is_selected": m(c["hit"]), "lip_corr_vs_neutral": m(c["lipc"])}
                      for (a, b), c in cell.items()},
           "neutral_selected_leak": {a: m(v) for a, v in leak.items()},
           "intensity_response": {e: {str(k): m(v) for k, v in d.items()} for e, d in inten.items()}}
    hits_match = [c["hit"] for (a, b), c in cell.items() if a == b]
    hits_cross = [c["hit"] for (a, b), c in cell.items() if a != b]
    res["nearest_accuracy"] = {"voice_matches_selection": m(np.concatenate(hits_match)),
                               "voice_differs_from_selection": m(np.concatenate(hits_cross))}
    print(json.dumps(res, indent=1))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
