"""Safety controls that live in the engine so no caller can skip them."""
from __future__ import annotations

import numpy as np

from .constants import WATERMARK_TEXT


class Watermark:
    """Burns a visible "AI-generated" label into the bottom-left corner of each frame.

    The label is rendered once per frame size and alpha-blended, so the per-frame
    cost is a small array blend.
    """

    def __init__(self, text: str = WATERMARK_TEXT, opacity: float = 0.85):
        self.text = text
        self.opacity = float(opacity)
        self._cache: dict[tuple[int, int], tuple[slice, slice, np.ndarray, np.ndarray]] = {}

    def _build(self, h: int, w: int):
        import cv2

        scale = max(0.35, min(h, w) / 512 * 0.6)
        thick = max(1, int(round(scale * 2)))
        (tw, th), base = cv2.getTextSize(self.text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        pad = max(3, int(round(6 * scale)))
        bw, bh = min(w, tw + 2 * pad), min(h, th + base + 2 * pad)
        patch = np.zeros((bh, bw, 3), dtype=np.uint8)  # dark plate
        alpha = np.full((bh, bw, 1), 0.55 * self.opacity, dtype=np.float32)
        text_mask = np.zeros((bh, bw), dtype=np.uint8)
        cv2.putText(text_mask, self.text, (pad, pad + th), cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thick, cv2.LINE_AA)
        m = (text_mask.astype(np.float32) / 255.0)[..., None]
        patch = (patch * (1 - m) + 255 * m).astype(np.uint8)
        alpha = np.maximum(alpha, m * self.opacity)
        margin = max(2, int(round(8 * scale)))
        ys = slice(h - bh - margin, h - margin) if h - bh - margin >= 0 else slice(0, bh)
        xs = slice(margin, margin + bw) if margin + bw <= w else slice(0, bw)
        return ys, xs, patch.astype(np.float32), alpha

    def apply(self, frame: np.ndarray) -> np.ndarray:
        """frame: HxWx3 uint8 (modified in place and returned)."""
        h, w = frame.shape[:2]
        key = (h, w)
        if key not in self._cache:
            self._cache[key] = self._build(h, w)
        ys, xs, patch, alpha = self._cache[key]
        region = frame[ys, xs].astype(np.float32)
        frame[ys, xs] = (region * (1 - alpha) + patch * alpha + 0.5).astype(np.uint8)
        return frame


class ConsentError(PermissionError):
    """Raised when a session is started without the user's explicit consent."""


def require_consent(portrait_consent: bool, audio_consent: bool) -> None:
    if not (portrait_consent and audio_consent):
        raise ConsentError(
            "A session needs explicit consent for both the portrait and the audio: the person shown "
            "must have agreed to be animated, and the speaker must have agreed to be processed."
        )
