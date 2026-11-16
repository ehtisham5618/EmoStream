"""Does per-frame feature streaming (hop 1) change what the behaviour model predicts?

Training features were computed with a hop of five frames, so a frame's feature comes
from any of five positions inside its encoder window. With hop 1 every frame comes from
the last valid position (least look-ahead). This script computes both kinds of features
for the same validation clips on CPU and compares the model's lip motion against the
ground truth under each.

    python -m evaluation.benchmarks.feature_hop_check --onnx outputs/local/aux/hubert.onnx \
        --pack outputs/local/M005.npz --wav-dir outputs/local/gt_m005 --checkpoints a.pt b.pt
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import soundfile as sf
import torch

from emostream.audio.features import StreamingHubert
from emostream.constants import EXP_DIM, LIP_KEYPOINTS
from emostream.models import BehaviourNet
from emostream.training.data import emotion_vector, shift_features, to_delta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--pack", required=True)
    ap.add_argument("--wav-dir", required=True)
    ap.add_argument("--checkpoints", nargs="+", required=True)
    ap.add_argument("--max-clips", type=int, default=24)
    ap.add_argument("--out", default="")
    ap.add_argument("--positions", type=int, nargs="*", default=[4],
                    help="read-out slots for per-frame streaming (0 = most look-ahead, 4 = least)")
    args = ap.parse_args()

    z = np.load(args.pack)
    ids = z["clip_ids"].tolist()
    ends = np.cumsum(z["lengths"])
    starts = ends - z["lengths"]
    mot = np.concatenate([z["exp"], z["pose"], z["t"][:, :2], z["scale"].reshape(-1, 1)], 1).astype(np.float32)
    neutral = [i for i, e in enumerate(z["emotions"]) if e == "neutral"]
    rest = np.median(np.concatenate([mot[starts[i]:starts[i] + 3] for i in neutral]), 0)
    lip = np.zeros((21, 3), bool)
    lip[list(LIP_KEYPOINTS)] = True
    lip = lip.reshape(-1)

    hub = StreamingHubert(args.onnx)
    clips = []
    for i in neutral[: args.max_clips]:
        wav = os.path.join(args.wav_dir, ids[i] + ".wav")
        if not os.path.exists(wav):
            continue
        audio, _ = sf.read(wav, dtype="float32")
        y = to_delta(mot[starts[i]:ends[i]].copy(), rest)
        n = min(len(y), -(-len(audio) // 640))
        c = {"y": y[:n], "stored": z["hubert"][starts[i]:starts[i] + n].astype(np.float32),
             "hop5": hub.features(audio)[:n]}
        for pos in args.positions:
            c[f"hop1_p{pos}"] = hub.features_per_frame(audio, pos)[:n]
        clips.append(c)
        print(f"clip {len(clips)} features done", flush=True)
    res = {"clips": len(clips), "feature_agreement": {}, "models": {}}
    kinds = ["hop5"] + [f"hop1_p{p}" for p in args.positions]
    for kind in kinds:
        c = [np.corrcoef(cl[kind].ravel(), cl["stored"].ravel())[0, 1] for cl in clips]
        res["feature_agreement"][f"{kind}_vs_stored_corr"] = round(float(np.mean(c)), 4)

    emo = emotion_vector("neutral", 1)
    for path in args.checkpoints:
        net = BehaviourNet.load(torch.load(path, map_location="cpu", weights_only=False))
        L = int(getattr(net.cfg, "lookahead", 0))
        row = {"lookahead": L}
        for kind in ["stored"] + kinds:
            corr, amp_p, amp_g = [], [], []
            for cl in clips:
                x = shift_features(cl[kind], L)
                with torch.no_grad():
                    e = torch.from_numpy(emo)[None, None].expand(1, len(x), -1)
                    p = net(torch.from_numpy(x)[None], e)[0][0].numpy()
                pl, yl = p[:, :EXP_DIM][:, lip], cl["y"][:, :EXP_DIM][:, lip]
                moving = yl.std(0) > 0.5 * yl.std(0).max()
                corr.append(np.mean([np.corrcoef(pl[:, j], yl[:, j])[0, 1] for j in np.where(moving)[0]]))
                amp_p.append(pl[:, moving].std(0).mean())
                amp_g.append(yl[:, moving].std(0).mean())
            row[kind] = {"lip_corr": round(float(np.mean(corr)), 3),
                         "lip_amp": round(float(np.sum(amp_p) / np.sum(amp_g)), 3)}
        res["models"][os.path.basename(path)] = row
    print(json.dumps(res, indent=1))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
