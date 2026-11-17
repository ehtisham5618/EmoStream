"""Lip normalisation for portraits whose mouth is open.

The behaviour model predicts motion relative to a neutral, closed-mouth rest pose, and the
engine adds it to the portrait's own pose. If the uploaded photo shows an open mouth (a
laugh, a wide smile), the avatar's "rest" is that open mouth and it never closes.

LivePortrait ships a small retargeting network for exactly this case: given the source
keypoints and the source's lip-opening ratio, it returns the keypoint offset that brings
the lips to a closed state before animation. This module loads that network (weights
``retargeting_models/stitching_retargeting_module.pth`` from KlingTeam/LivePortrait, MIT)
and computes the offset once per portrait.

The network definition follows ``src/modules/stitching_retargeting_network.py`` of
LivePortrait (MIT licence, Kuaishou Visual Generation and Interaction Center).
"""
from __future__ import annotations

import numpy as np

# Below this lip-opening ratio the mouth counts as closed and nothing is changed
# (LivePortrait's own default, ``lip_normalize_threshold``).
LIP_OPEN_THRESHOLD = 0.03

# How far an open mouth is closed. LivePortrait closes to ratio 0. For a clearly open mouth
# (ratio >= 0.2) that overshoots: the lips are pressed together and speech can no longer open
# them (user portrait, ratio 0.31: vowel openings 20-25 % of a real speaker's, 17 Nov 2026).
# Closing such portraits to a relaxed ratio of 0.15 gave the best match to real speakers
# (docs/iterations/current_iteration/bilabial_closure_experiments.md). Slightly open portraits
# keep ratio 0 (validated on MEAD: evaluation portrait ratio 0.12, closure recall 0.90).
WIDE_OPEN_RATIO = 0.2
RELAXED_TARGET = 0.15


def lip_target_for(ratio: float) -> float:
    return RELAXED_TARGET if ratio >= WIDE_OPEN_RATIO else 0.0


def lip_open_ratio(lmk203: np.ndarray) -> float:
    """Inner-lip gap divided by mouth width, from the 203-point landmarks
    (indices as in LivePortrait's ``calc_lip_close_ratio``)."""
    lmk = np.asarray(lmk203, dtype=np.float32).reshape(-1, 2)
    gap = np.linalg.norm(lmk[90] - lmk[102])
    width = np.linalg.norm(lmk[48] - lmk[66])
    return float(gap / (width + 1e-6))


def build_lip_retargeter(checkpoint_path: str, device: str = "cuda"):
    import torch
    from torch import nn

    sizes = [65, 128, 128, 64, 63]  # (21*3 + 2) -> 63, as in LivePortrait's models.yaml
    layers = []
    for i in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[i], sizes[i + 1]))
        if i < len(sizes) - 2:
            layers.append(nn.ReLU(inplace=True))

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.mlp = nn.Sequential(*layers)

        def forward(self, x):
            return self.mlp(x)

    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = {k.replace("module.", ""): v for k, v in ckpt["retarget_mouth"].items()}
    net = Net()
    net.load_state_dict(state)
    return net.to(device).eval()


def lip_close_offset(net, x_s_keypoints: np.ndarray, ratio: float, device: str = "cuda", target: float = 0.0,
                     strength: float = 1.0) -> np.ndarray:
    """Keypoint offset (1, 21, 3) that brings the source's lip-opening ratio to ``target``
    (0 = fully closed, LivePortrait's default), scaled by ``strength``."""
    import torch

    feat = np.concatenate([np.asarray(x_s_keypoints, dtype=np.float32).reshape(1, -1),
                           np.array([[ratio, target]], dtype=np.float32)], 1)
    with torch.no_grad():
        delta = net(torch.from_numpy(feat).to(device))
    return strength * delta.float().cpu().numpy().reshape(1, 21, 3)
