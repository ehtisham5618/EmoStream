"""Streaming WavLM speech features: one 768-d vector per 40 ms video frame.

Why: on validation actors, a linear probe recovers lip motion 26 % better from WavLM-base-plus
(layer 6, live context) than from Ditto's streaming HuBERT (0.384 vs 0.304,
docs/evaluation/data/feature_encoder_probe_streaming.json).

Definition (identical offline and live, so training and serving see the same features):

* Frame k's feature is computed from the audio segment
  ``[max(0, (k + 1) * 640 - past), (k + 1 + future) * 640)`` samples at 16 kHz,
  i.e. up to ``past`` samples of history and ``future`` frames of look-ahead.
  Audio beyond the end of a stream is silence.
* WavLM emits one vector per 320 samples. Segments start on a frame boundary, so frame k
  is segment frame m = k - start / 640, and its feature is the mean of encoder vectors
  2m and 2m + 1 of hidden layer ``layer``.

Offline, frames with a full history all have equal-length segments and are batched;
the first frames (shorter history) are computed one at a time, exactly as live.
"""
from __future__ import annotations

import numpy as np

SR = 16000
FRAME = 640
REPO = "microsoft/wavlm-base-plus"


class WavLMFeatures:
    def __init__(self, layer: int = 6, past_s: float = 1.0, future_frames: int = 2, device: str = "cpu",
                 repo: str = REPO, model=None, extractor=None):
        import torch
        from transformers import AutoFeatureExtractor, WavLMModel

        self.torch = torch
        self.layer, self.future = layer, future_frames
        self.past = int(round(past_s * SR / FRAME)) * FRAME          # whole frames of history
        self.device = device
        self.fe = extractor or AutoFeatureExtractor.from_pretrained(repo)
        self.model = (model or WavLMModel.from_pretrained(repo)).to(device).eval()
        self.dim = self.model.config.hidden_size

    @property
    def config(self) -> dict:
        return {"encoder": "wavlm-base-plus", "layer": self.layer, "past_samples": self.past,
                "future_frames": self.future}

    def segment(self, audio: np.ndarray, k: int) -> tuple[np.ndarray, int]:
        """Segment for frame k and its start frame; pads with silence past the end."""
        start = max(0, (k + 1) * FRAME - self.past)
        end = (k + 1 + self.future) * FRAME
        seg = audio[start:end]
        if len(seg) < end - start:
            seg = np.concatenate([seg, np.zeros(end - start - len(seg), np.float32)])
        return seg.astype(np.float32), start // FRAME

    def _encode(self, segs: list[np.ndarray]) -> np.ndarray:
        torch = self.torch
        inp = self.fe(segs, sampling_rate=SR, return_tensors="pt", padding=False)
        with torch.no_grad():
            h = self.model(inp.input_values.to(self.device), output_hidden_states=True).hidden_states[self.layer]
        return h.float().cpu().numpy()

    def frames(self, audio: np.ndarray, n_frames: int, batch: int = 64) -> np.ndarray:
        """Offline: features of frames 0 .. n_frames-1 of a whole recording."""
        out = np.zeros((n_frames, self.dim), np.float32)
        full_from = self.past // FRAME - 1                 # first frame with a complete history
        for k in range(min(full_from, n_frames)):
            out[k] = self._frame_from(*self.segment(audio, k), k)
        ks = list(range(full_from, n_frames))
        for i in range(0, len(ks), batch):
            chunk = ks[i:i + batch]
            segs = [self.segment(audio, k) for k in chunk]
            h = self._encode([s for s, _ in segs])
            for j, (k, (_, start)) in enumerate(zip(chunk, segs)):
                m = k - start
                out[k] = h[j, 2 * m:2 * m + 2].mean(0)
        return out

    def frames_many(self, audios: list[np.ndarray], lengths: list[int], batch: int = 64) -> list[np.ndarray]:
        """Offline, many clips at once: every (clip, frame) segment of equal length is batched,
        including the short-history frames at clip starts (frame k has the same segment
        length in every clip). Gives exactly ``frames`` per clip."""
        outs = [np.zeros((n, self.dim), np.float32) for n in lengths]
        groups: dict[int, list[tuple[int, int]]] = {}
        for c, n in enumerate(lengths):
            for k in range(n):
                seg_len = (k + 1 + self.future) * FRAME - max(0, (k + 1) * FRAME - self.past)
                groups.setdefault(seg_len, []).append((c, k))
        for items in groups.values():
            for i in range(0, len(items), batch):
                chunk = items[i:i + batch]
                segs = [self.segment(audios[c], k) for c, k in chunk]
                h = self._encode([s for s, _ in segs])
                for j, ((c, k), (_, start)) in enumerate(zip(chunk, segs)):
                    m = k - start
                    outs[c][k] = h[j, 2 * m:2 * m + 2].mean(0)
        return outs

    def _frame_from(self, seg: np.ndarray, start: int, k: int) -> np.ndarray:
        h = self._encode([seg])[0]
        m = k - start
        return h[2 * m:2 * m + 2].mean(0)


class WavLMStream:
    """Live: feed audio in any chunk size; returns features for every frame whose
    look-ahead has arrived. ``flush(total)`` pads silence to finish the stream."""

    def __init__(self, extractor: WavLMFeatures):
        self.x = extractor
        self.buf = np.zeros(0, np.float32)
        self.offset = 0          # sample index of buf[0]
        self.next = 0            # next frame to compute

    def _ready(self, k: int, total_samples: int) -> bool:
        return (k + 1 + self.x.future) * FRAME <= total_samples

    def _compute(self, k: int) -> np.ndarray:
        start = max(0, (k + 1) * FRAME - self.x.past)
        end = (k + 1 + self.x.future) * FRAME
        seg = self.buf[start - self.offset:end - self.offset]
        if len(seg) < end - start:
            seg = np.concatenate([seg, np.zeros(end - start - len(seg), np.float32)])
        return self.x._frame_from(seg, start // FRAME, k)

    def _trim(self) -> None:
        keep_from = max(0, (self.next + 1) * FRAME - self.x.past)
        if keep_from > self.offset:
            self.buf = self.buf[keep_from - self.offset:]
            self.offset = keep_from

    def push(self, audio: np.ndarray) -> np.ndarray:
        self.buf = np.concatenate([self.buf, np.asarray(audio, np.float32)])
        total = self.offset + len(self.buf)
        out = []
        while self._ready(self.next, total):
            out.append(self._compute(self.next))
            self.next += 1
            self._trim()
        return np.stack(out) if out else np.zeros((0, self.x.dim), np.float32)

    def flush(self, total_frames: int) -> np.ndarray:
        out = []
        while self.next < total_frames:
            out.append(self._compute(self.next))
            self.next += 1
            self._trim()
        return np.stack(out) if out else np.zeros((0, self.x.dim), np.float32)

    @property
    def delay_frames(self) -> int:
        return self.x.future
