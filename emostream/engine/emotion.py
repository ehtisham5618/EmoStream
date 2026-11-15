"""Emotion state over time: which emotion and intensity applies to each video frame."""
from __future__ import annotations

import bisect

import numpy as np

from ..constants import DITTO_EMOTIONS, EMOSTREAM_TO_DITTO, EMOTION_TO_ID, EMOTIONS


def validate(emotion: str, intensity: float) -> tuple[str, float]:
    if emotion not in EMOTION_TO_ID:
        raise ValueError(f"unknown emotion {emotion!r}; expected one of {EMOTIONS}")
    intensity = float(intensity)
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("intensity must be in [0, 1]")
    return emotion, intensity


class EmotionTimeline:
    """Piecewise-constant emotion targets keyed by the frame at which they start.

    ``set(emotion, intensity, at_frame)`` schedules a change; ``at(frame)`` returns the
    target in force at that frame. A change scheduled in the past of an already
    generated frame only affects frames that have not been generated yet, because
    the engine asks for targets frame by frame as it generates.
    """

    def __init__(self, emotion: str = "neutral", intensity: float = 1.0):
        e, a = validate(emotion, intensity)
        self._frames = [0]
        self._targets = [(e, a)]

    def set(self, emotion: str, intensity: float = 1.0, at_frame: int = 0) -> None:
        e, a = validate(emotion, intensity)
        at_frame = max(0, int(at_frame))
        i = bisect.bisect_left(self._frames, at_frame)
        if i < len(self._frames) and self._frames[i] == at_frame:
            self._targets[i] = (e, a)
        else:
            self._frames.insert(i, at_frame)
            self._targets.insert(i, (e, a))
        # A new target replaces anything previously scheduled after it.
        del self._frames[i + 1:]
        del self._targets[i + 1:]

    def at(self, frame: int) -> tuple[str, float]:
        i = bisect.bisect_right(self._frames, max(0, int(frame))) - 1
        return self._targets[i]

    def changes(self) -> list[tuple[int, str, float]]:
        return [(f, e, a) for f, (e, a) in zip(self._frames, self._targets)]

    def blended(self, frame: int, vector_fn, fade_frames: int = 0) -> np.ndarray:
        """Conditioning vector at ``frame`` with a linear cross-fade over ``fade_frames``
        after each change (the transition gate). ``vector_fn(emotion, intensity)`` maps
        a target to a vector. With ``fade_frames=0`` the change is a hard switch."""
        frame = max(0, int(frame))
        i = bisect.bisect_right(self._frames, frame) - 1
        cur = vector_fn(*self._targets[i])
        if fade_frames <= 0 or i == 0:
            return cur
        k = frame - self._frames[i]
        if k >= fade_frames:
            return cur
        # Fade from where the previous transition had got to at the moment of this change.
        prev = self.blended(self._frames[i] - 1, vector_fn, fade_frames)
        w = (k + 1) / (fade_frames + 1)
        return ((1.0 - w) * prev + w * cur).astype(np.float32)


def one_hot_with_intensity(emotion: str, intensity: float) -> np.ndarray:
    """EmoStream's own conditioning vector: 5 values, the emotion's slot holds the
    intensity and the neutral slot the remainder, so intensity 0 equals neutral."""
    e, a = validate(emotion, intensity)
    v = np.zeros(len(EMOTIONS), dtype=np.float32)
    if e == "neutral":
        v[EMOTION_TO_ID["neutral"]] = 1.0
    else:
        v[EMOTION_TO_ID[e]] = a
        v[EMOTION_TO_ID["neutral"]] = 1.0 - a
    return v


def _ditto_soft(idx: int) -> np.ndarray:
    # Same construction as Ditto's _get_emo_avg: softmax of an 8-vector with 8 at idx.
    z = np.zeros(len(DITTO_EMOTIONS), dtype=np.float64)
    z[idx] = 8.0
    z = np.exp(z - z.max())
    return (z / z.sum()).astype(np.float32)


def ditto_emotion_vector(emotion: str, intensity: float) -> np.ndarray:
    """8-way soft emotion vector for Ditto's motion model. Intensity interpolates
    between the neutral vector and the target emotion's vector."""
    e, a = validate(emotion, intensity)
    neutral = _ditto_soft(EMOSTREAM_TO_DITTO["neutral"])
    if e == "neutral":
        return neutral
    return ((1.0 - a) * neutral + a * _ditto_soft(EMOSTREAM_TO_DITTO[e])).astype(np.float32)
