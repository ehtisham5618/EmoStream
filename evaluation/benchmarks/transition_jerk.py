"""Emotion-transition smoothness in motion space (CPU, no renderer needed).

For neutral-speech clips of a validation actor, the emotion is switched from neutral
to each target emotion half-way through the clip. The behaviour model is run twice on
identical audio: with a hard switch, and with the transition gate (linear cross-fade of
the conditioning vector over ``fade`` frames). Boundary jerk is the mean absolute third
difference of the predicted motion in the ±5 frames around the switch.

    python -m evaluation.benchmarks.transition_jerk --checkpoint outputs/local/reg_model.pt \
        --pack outputs/local/M005.npz
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import torch

from emostream.constants import EMOTIONS, EXP_DIM
from emostream.engine.emotion import EmotionTimeline, one_hot_with_intensity
from emostream.metrics.motion import boundary_jerk, smoothness
from emostream.models import BehaviourNet


def run(net, audio: np.ndarray, timeline: EmotionTimeline, fade: int, chunk: int = 5) -> np.ndarray:
    """Streams a clip through the model in 5-frame blocks, as the engine does."""
    outs, state = [], None
    with torch.no_grad():
        for i in range(0, len(audio), chunk):
            a = torch.from_numpy(audio[i:i + chunk].astype(np.float32))[None]
            e = torch.from_numpy(np.stack([timeline.blended(i + k, one_hot_with_intensity, fade)
                                           for k in range(a.shape[1])]))[None]
            o, state = net(a, e, state)
            outs.append(o[0].numpy())
    return np.concatenate(outs, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--pack", required=True, help="per-actor feature pack of a validation actor")
    ap.add_argument("--fades", default="5,10,15")
    ap.add_argument("--max-clips", type=int, default=40)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    net = BehaviourNet.load(torch.load(args.checkpoint, map_location="cpu", weights_only=False))
    z = np.load(args.pack)
    ends = np.cumsum(z["lengths"])
    starts = ends - z["lengths"]
    hub = z["hubert"]
    clips = [(int(s), int(e)) for s, e, emo in zip(starts, ends, z["emotions"]) if emo == "neutral" and e - s >= 60]
    clips = clips[: args.max_clips]
    scale = net.out_scale.numpy()  # compare in standardised units so no coordinate dominates

    fades = [int(x) for x in args.fades.split(",")]
    res = {"checkpoint": args.checkpoint, "pack": args.pack, "clips": len(clips), "half_window_frames": 5,
           "by_fade": {}}
    for fade in fades:
        rows = {}
        for emo in EMOTIONS[1:]:
            hard, soft, away = [], [], []
            for s, e in clips:
                audio = hub[s:e]
                b = len(audio) // 2
                tl = EmotionTimeline("neutral")
                tl.set(emo, 1.0, at_frame=b)
                m_hard = run(net, audio, tl, 0) / scale
                m_soft = run(net, audio, tl, fade) / scale
                hard.append(boundary_jerk(m_hard[:, :EXP_DIM], b))
                soft.append(boundary_jerk(m_soft[:, :EXP_DIM], b))
                away.append(smoothness(m_hard[: b - 10, :EXP_DIM])["jerk"])
            h, sft = float(np.mean(hard)), float(np.mean(soft))
            rows[emo] = {"hard_switch": round(h, 2), "with_gate": round(sft, 2),
                         "reduction": round(1 - sft / h, 3), "jerk_away_from_switch": round(float(np.mean(away)), 2)}
        rows["mean_reduction"] = round(float(np.mean([r["reduction"] for r in rows.values()])), 3)
        res["by_fade"][str(fade)] = rows
    print(json.dumps(res, indent=1))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
