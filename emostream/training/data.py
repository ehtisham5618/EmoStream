"""Training data for the behaviour model: MEAD motion targets and speech features.

Targets are motion *deltas* relative to each actor's neutral rest pose, so the model
does not have to learn any actor's face shape:

    y = motion(frame) - rest(actor)

``rest(actor)`` is the median of the first frames of that actor's neutral clips (mouth
closed, before speech starts).

The articulation branch is trained on a second target, ``y_art``, from which the
clip's static emotional offset has been removed:

    y_art = y - (mean_t y(clip) - neutral_speaking_mean(actor))

so it learns how the mouth moves with speech regardless of the acted emotion, while the
emotion branch has to explain what is left (the offset and emotion-specific dynamics).
"""
from __future__ import annotations

import json
from collections import defaultdict

import numpy as np

from ..constants import EMOTION_TO_ID, EMOTIONS, EXP_DIM, LIP_KEYPOINTS
from ..models.behaviour_net import MOTION_DIM

MAX_LEVEL = 3


def motion_vector(z) -> np.ndarray:
    """npz fields -> (T, 69): exp, pose (deg), translation x/y, scale."""
    T = z["exp"].shape[0]
    return np.concatenate([z["exp"].reshape(T, EXP_DIM), z["pose"].reshape(T, 3), z["t"].reshape(T, 3)[:, :2],
                           z["scale"].reshape(T, 1)], 1).astype(np.float32)


def emotion_vector(emotion: str, level: int) -> np.ndarray:
    v = np.zeros(len(EMOTIONS), dtype=np.float32)
    if emotion == "neutral":
        v[0] = 1.0
    else:
        a = level / MAX_LEVEL
        v[EMOTION_TO_ID[emotion]] = a
        v[0] = 1.0 - a
    return v


def load_index(path: str, split: str) -> list[dict]:
    return [r for r in map(json.loads, open(path)) if r["split"] == split]


def actor_references(clips: list[dict]) -> dict:
    """Per actor: rest pose (median of first frames of neutral clips) and the mean motion
    while speaking neutrally. ``clips`` carry a loaded ``motion`` array."""
    first, speak = defaultdict(list), defaultdict(list)
    for c in clips:
        if c["emotion"] == "neutral":
            first[c["actor"]].append(c["motion"][:3])
            speak[c["actor"]].append(c["motion"])
    refs = {}
    for a in first:
        rest = np.median(np.concatenate(first[a], 0), 0)
        refs[a] = {"rest": rest, "neutral_mean": np.concatenate(speak[a], 0).mean(0) - rest}
    return refs


def to_delta(motion: np.ndarray, rest: np.ndarray) -> np.ndarray:
    y = motion - rest
    y[:, -1] = motion[:, -1] / rest[-1] - 1.0  # scale as a ratio
    return y


def shift_features(audio: np.ndarray, lookahead: int) -> np.ndarray:
    """Input for frame t becomes the feature of frame t + lookahead (the last feature is
    repeated at the end). The model then sees ``lookahead`` more frames of future audio,
    at the price of ``lookahead * 40`` ms more delay in a live stream."""
    if lookahead <= 0:
        return audio
    return np.concatenate([audio[lookahead:], np.repeat(audio[-1:], min(lookahead, len(audio)), 0)], 0)


def lip_columns() -> np.ndarray:
    m = np.zeros((21, 3), bool)
    m[list(LIP_KEYPOINTS)] = True
    return np.where(m.reshape(-1))[0]


def opening_axis(clips: list[dict]) -> np.ndarray:
    """First principal component of lip-keypoint motion in the articulation targets: in MEAD
    this is the mouth-opening direction (jaw drop and lip separation)."""
    cols = lip_columns()
    y = np.concatenate([c["y_art"][:, cols] for c in clips], 0)[::3]
    y = y - y.mean(0)
    ax = np.linalg.svd(y, full_matrices=False)[2][0]
    # orient it so that larger means more open: speech frames open more than the clip start
    probe = np.concatenate([c["y_art"][:, cols] @ ax for c in clips[:200]])
    return ax if np.percentile(probe, 90) - np.median(probe) > np.median(probe) - np.percentile(probe, 10) else -ax


CLOSED_FRACTION = 0.2


class ClipSet:
    """All clips of one split in memory, with deltas and articulation targets."""

    def __init__(self, index: list[dict], loader=np.load, lookahead: int = 0, axis: np.ndarray | None = None):
        self.clips = []
        self.lookahead = lookahead
        for r in index:
            z = loader(r["features"])
            c = {**r, "motion": motion_vector(z), "audio": shift_features(np.asarray(z["hubert"]), lookahead)}
            if "hubert_aug" in z:
                c["audio_aug"] = shift_features(np.asarray(z["hubert_aug"]), lookahead)
            if "viseme" in z:
                c["viseme"] = np.asarray(z["viseme"]).astype(np.int64)
            self.clips.append(c)
        self.refs = actor_references(self.clips)
        kept = []
        for c in self.clips:
            ref = self.refs.get(c["actor"])
            if ref is None:      # actor without neutral clips: cannot define a rest pose
                continue
            y = to_delta(c.pop("motion"), ref["rest"])
            offset = y.mean(0) - ref["neutral_mean"]
            c["y"] = y
            c["y_art"] = y - offset
            c["emo"] = emotion_vector(c["emotion"], c["level"])
            kept.append(c)
        self.clips = kept
        # Frames where the real mouth is among the most closed of its clip (bilabial
        # closures, pauses). Used to weight the loss where articulation errors are most visible.
        self.axis = opening_axis(self.clips) if axis is None and self.clips else axis
        cols = lip_columns()
        for c in self.clips:
            o = c["y_art"][:, cols] @ self.axis
            c["closed"] = (o <= np.quantile(o, CLOSED_FRACTION)).astype(np.float32)

    def __len__(self):
        return len(self.clips)

    def stats(self) -> np.ndarray:
        """Per-dimension standard deviation of the targets, floored so that nearly
        constant coordinates do not dominate a normalised loss."""
        y = np.concatenate([c["y"] for c in self.clips], 0)
        std = y.std(0)
        for sl in (slice(0, EXP_DIM), slice(EXP_DIM, EXP_DIM + 3), slice(EXP_DIM + 3, EXP_DIM + 5),
                   slice(MOTION_DIM - 1, MOTION_DIM)):
            std[sl] = np.maximum(std[sl], 0.25 * np.median(std[sl]))
        return np.maximum(std, 1e-6).astype(np.float32)  # a constant coordinate must not divide by zero

    def batch(self, rng: np.random.Generator, batch_size: int, length: int, aug_prob: float = 0.0):
        """Random crops. Returns audio (B, L, D), emo (B, L, 5), y, y_art (B, L, 69), mask (B, L),
        closed (B, L), viseme (B, L) with -1 where unlabelled.
        ``aug_prob``: chance that a sample uses its degraded-audio features (if present)."""
        idx = rng.integers(0, len(self.clips), batch_size)
        D = self.clips[0]["audio"].shape[1]
        audio = np.zeros((batch_size, length, D), np.float32)
        emo = np.zeros((batch_size, length, len(EMOTIONS)), np.float32)
        y = np.zeros((batch_size, length, MOTION_DIM), np.float32)
        y_art = np.zeros_like(y)
        mask = np.zeros((batch_size, length), np.float32)
        closed = np.zeros((batch_size, length), np.float32)
        vis = np.full((batch_size, length), -1, np.int64)
        for b, i in enumerate(idx):
            c = self.clips[i]
            T = len(c["y"])
            n = min(T, length)
            # Always start at the clip start half of the time so the model sees stream starts.
            s = 0 if (T <= length or rng.random() < 0.5) else int(rng.integers(0, T - length + 1))
            src = c["audio_aug"] if ("audio_aug" in c and rng.random() < aug_prob) else c["audio"]
            audio[b, :n] = src[s:s + n]
            if "viseme" in c:
                vis[b, :n] = c["viseme"][s:s + n]
            y[b, :n] = c["y"][s:s + n]
            y_art[b, :n] = c["y_art"][s:s + n]
            closed[b, :n] = c["closed"][s:s + n]
            emo[b, :n] = c["emo"]
            emo[b, n:, 0] = 1.0
            mask[b, :n] = 1.0
        return audio, emo, y, y_art, mask, closed, vis
