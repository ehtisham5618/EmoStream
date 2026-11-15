"""EmoStream behaviour model: streaming speech features + emotion -> LivePortrait motion.

The model predicts, per 40 ms frame, a motion *delta* relative to a neutral rest pose:

    63  expression offsets (21 implicit keypoints x 3)
     3  head rotation in degrees (pitch, yaw, roll)
     2  head translation (x, y)
     1  relative scale

Two branches:

* **Articulation** sees only speech features and predicts what the mouth does.
* **Emotion** sees speech features, the emotion class and the intensity, and predicts
  an expression residual plus head pose. Its output is multiplied by the intensity, so
  intensity 0 (or the neutral class) reproduces the articulation branch exactly.

**Region-aware fusion.** The emotion residual is added through a per-coordinate gate.
On lip keypoints the gate is capped (``lip_cap``), so an emotion can shape the mouth
(a smile, a frown) but cannot override the articulation that carries lip sync.

Everything is causal: a linear projection and unidirectional GRUs, so processing audio
in chunks of any size gives the same result as processing it in one piece, provided
the hidden state is carried over. The only look-ahead is the 85 ms inside the speech
encoder.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
from torch import nn

from ..constants import EMOTIONS, EXP_DIM, EYE_KEYPOINTS, LIP_KEYPOINTS, N_KEYPOINTS

POSE_DIM = 3
TRANS_DIM = 2
MOTION_DIM = EXP_DIM + POSE_DIM + TRANS_DIM + 1  # 69


def keypoint_mask(keypoints) -> torch.Tensor:
    """63-vector with ones on the three coordinates of each listed keypoint."""
    m = torch.zeros(N_KEYPOINTS, 3)
    m[list(keypoints)] = 1.0
    return m.reshape(-1)


@dataclass
class BehaviourConfig:
    audio_dim: int = 1024
    hidden: int = 256
    layers: int = 2
    emo_hidden: int = 192
    emo_embed: int = 32
    dropout: float = 0.1
    lip_cap: float = 0.35          # upper bound of the emotion gate on lip coordinates
    n_emotions: int = len(EMOTIONS)


class BehaviourNet(nn.Module):
    def __init__(self, cfg: BehaviourConfig | None = None):
        super().__init__()
        self.cfg = cfg = cfg or BehaviourConfig()
        self.audio_in = nn.Sequential(nn.Linear(cfg.audio_dim, cfg.hidden), nn.LayerNorm(cfg.hidden), nn.GELU(),
                                      nn.Dropout(cfg.dropout))
        # articulation branch
        self.art_rnn = nn.GRU(cfg.hidden, cfg.hidden, cfg.layers, batch_first=True,
                              dropout=cfg.dropout if cfg.layers > 1 else 0.0)
        self.art_out = nn.Linear(cfg.hidden, EXP_DIM)
        # emotion branch: emotion vector (class slots weighted by intensity) + intensity scalar
        self.emo_in = nn.Sequential(nn.Linear(cfg.n_emotions + 1, cfg.emo_embed), nn.GELU())
        self.emo_rnn = nn.GRU(cfg.hidden + cfg.emo_embed, cfg.emo_hidden, 1, batch_first=True)
        self.emo_exp = nn.Linear(cfg.emo_hidden, EXP_DIM)
        self.emo_head = nn.Linear(cfg.emo_hidden, POSE_DIM + TRANS_DIM + 1)
        # head pose that does not depend on emotion (speech-driven nods), from articulation features
        self.art_head = nn.Linear(cfg.hidden, POSE_DIM + TRANS_DIM + 1)
        # region-aware gate
        self.gate_logit = nn.Parameter(torch.zeros(EXP_DIM))
        self.register_buffer("lip_mask", keypoint_mask(LIP_KEYPOINTS))
        self.register_buffer("eye_mask", keypoint_mask(EYE_KEYPOINTS))
        # output normalisation (set from training-set statistics; identity by default)
        self.register_buffer("out_scale", torch.ones(MOTION_DIM))
        nn.init.zeros_(self.emo_exp.weight)
        nn.init.zeros_(self.emo_exp.bias)

    # ------------------------------------------------------------------------------
    def emotion_gate(self) -> torch.Tensor:
        """Per-coordinate weight of the emotion residual: (0, 1) off the lips, (0, lip_cap) on them."""
        g = torch.sigmoid(self.gate_logit + 2.0)
        cap = 1.0 - self.lip_mask * (1.0 - self.cfg.lip_cap)
        return g * cap

    def init_state(self, batch: int = 1, device=None):
        device = device or self.gate_logit.device
        return (torch.zeros(self.cfg.layers, batch, self.cfg.hidden, device=device),
                torch.zeros(1, batch, self.cfg.emo_hidden, device=device))

    def forward(self, audio: torch.Tensor, emotion: torch.Tensor, state=None, return_parts: bool = False):
        """
        audio:   (B, T, audio_dim) speech features, one per video frame
        emotion: (B, T, n_emotions) class weights; the neutral slot holds 1 - intensity
        state:   hidden states from the previous chunk, or None at the start of a stream
        returns  motion (B, T, 69) in physical units, and the new state
        """
        if state is None:
            state = self.init_state(audio.shape[0], audio.device)
        h_art, h_emo = state
        intensity = 1.0 - emotion[..., :1]                     # neutral slot is index 0
        a = self.audio_in(audio)
        art, h_art = self.art_rnn(a, h_art)
        e_in = self.emo_in(torch.cat([emotion, intensity], -1))
        emo, h_emo = self.emo_rnn(torch.cat([a, e_in], -1), h_emo)

        # Both branches produce a full 69-d motion in normalised units.
        art_out = torch.cat([self.art_out(art), self.art_head(art)], -1)
        emo_out = torch.cat([self.emo_exp(emo) * self.emotion_gate(), self.emo_head(emo)], -1) * intensity
        out = (art_out + emo_out) * self.out_scale
        if return_parts:
            return out, (h_art, h_emo), {"art": art_out * self.out_scale, "emo": emo_out * self.out_scale}
        return out, (h_art, h_emo)

    # ------------------------------------------------------------------------------
    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def export(self) -> dict:
        return {"config": asdict(self.cfg), "state_dict": self.state_dict()}

    @classmethod
    def load(cls, blob: dict) -> "BehaviourNet":
        net = cls(BehaviourConfig(**blob["config"]))
        net.load_state_dict(blob["state_dict"])
        return net.eval()


def split_motion(m: torch.Tensor):
    """(…, 69) -> exp (…, 63), pose (…, 3), trans (…, 2), scale (…, 1)."""
    return (m[..., :EXP_DIM], m[..., EXP_DIM:EXP_DIM + POSE_DIM],
            m[..., EXP_DIM + POSE_DIM:EXP_DIM + POSE_DIM + TRANS_DIM], m[..., -1:])
