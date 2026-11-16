"""Figures for the iteration report (numbers only; no faces).

    python -m evaluation.benchmarks.make_figures --pack outputs/local/packed/M005.npz \
        --reg outputs/local/reg_model.pt --new outputs/local/it_ccc_la2.pt \
        --intensity docs/evaluation/data/emotion_control_motion_it_ccc_la2.json \
        --out docs/iterations/current_iteration/figures
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

from emostream.models import BehaviourNet  # noqa: E402
from emostream.training.data import emotion_vector, shift_features, to_delta  # noqa: E402

INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"   # validated categorical order


def style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=12, fontweight="bold")
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.grid(True, axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)


def predict(net, feat, emotion="neutral", level=1):
    x = torch.from_numpy(shift_features(feat.astype(np.float32), int(getattr(net.cfg, "lookahead", 0))))[None]
    e = torch.from_numpy(emotion_vector(emotion, level))[None, None].expand(1, x.shape[1], -1)
    with torch.no_grad():
        return net(x, e)[0][0].numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--reg", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--intensity", required=True)
    ap.add_argument("--clip", default="M005_neutral_L1_009")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Sans"

    z = np.load(a.pack)
    ids = z["clip_ids"].tolist()
    ends = np.cumsum(z["lengths"])
    starts = ends - z["lengths"]
    mot = np.concatenate([z["exp"], z["pose"], z["t"][:, :2], z["scale"].reshape(-1, 1)], 1).astype(np.float32)
    neutral = [i for i, e in enumerate(z["emotions"]) if e == "neutral"]
    rest = np.median(np.concatenate([mot[starts[i]:starts[i] + 3] for i in neutral]), 0)
    i = ids.index(a.clip)
    y = to_delta(mot[starts[i]:ends[i]].copy(), rest)
    feat = z["hubert"][starts[i]:ends[i]]
    reg = BehaviourNet.load(torch.load(a.reg, map_location="cpu", weights_only=False))
    new = BehaviourNet.load(torch.load(a.new, map_location="cpu", weights_only=False))
    t = np.arange(len(y)) / 25.0
    d = 19 * 3 + 1          # keypoint 19, vertical: the coordinate that moves most in speech

    # ---- 1. lip trajectory -----------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8.6, 3.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    series = [("Real video", y[:, d] * 1000, INK2, 1.6), ("Previous (reg)", predict(reg, feat)[:, d] * 1000, ORANGE, 2.0),
              ("Improved", predict(new, feat)[:, d] * 1000, BLUE, 2.0)]
    for name, v, c, lw in series:
        ax.plot(t, v, color=c, linewidth=lw, label=name, solid_capstyle="round")
    style(ax, "Lower-lip movement during one unseen validation clip", "seconds",
          "vertical offset from rest (×10⁻³, renderer units)")
    ax.legend(frameon=False, fontsize=9, loc="upper right", labelcolor=INK2, ncol=3)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "lip_trajectory.png"), facecolor=SURFACE)
    plt.close(fig)

    # ---- 2. intensity response -------------------------------------------------------------
    resp = json.load(open(a.intensity))["intensity_response"]
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    xs = [0.0, 0.25, 0.5, 0.75, 1.0]
    for (emo, c) in zip(("happy", "sad", "angry", "surprised"), (BLUE, ORANGE, AQUA, YELLOW)):
        v = [resp[emo][str(k)] for k in xs]
        ax.plot(xs, v, color=c, linewidth=2, marker="o", markersize=5, label=emo.capitalize())
        ax.annotate(emo.capitalize(), (1.0, v[-1]), xytext=(6, 0), textcoords="offset points", fontsize=9,
                    color=INK2, va="center")
    style(ax, "Expression strength follows the intensity setting", "intensity setting",
          "share of the real full-strength expression")
    ax.set_xticks(xs)
    ax.set_xlim(-0.03, 1.22)
    ax.set_ylim(bottom=-0.02)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "intensity_response.png"), facecolor=SURFACE)
    plt.close(fig)
    print("figures written to", a.out)


if __name__ == "__main__":
    main()
