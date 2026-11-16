"""Speech features outside the GPU engine: Ditto's streaming HuBERT through ONNX Runtime.

Reproduces ``Wav2FeatHubert`` from the Ditto repository (window of 3 past, 5 valid and 2
future frames; two encoder steps averaged per video frame) so that analysis scripts and
CPU experiments use exactly the features the engine uses.
"""
from __future__ import annotations

import numpy as np

from .clock import SlidingWindowChunker


class StreamingHubert:
    def __init__(self, onnx_path: str, chunk=(3, 5, 2), providers=("CPUExecutionProvider",)):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3
        self.sess = ort.InferenceSession(onnx_path, so, providers=list(providers))
        self.chunk = tuple(chunk)

    def window(self, audio_window: np.ndarray, take: slice | None = None) -> np.ndarray:
        """One 6480-sample window -> features of its valid frames, (5, 1024)."""
        enc = self.sess.run(None, {"input_values": audio_window.astype(np.float32).reshape(1, -1)})[0]
        enc = enc.reshape(-1, enc.shape[-1])
        s, e = -sum(self.chunk[1:]) * 2, -self.chunk[2] * 2
        feat = enc[s:e].reshape(self.chunk[1], 2, -1).mean(1)
        return feat if take is None else feat[take]

    def features(self, audio: np.ndarray) -> np.ndarray:
        """Whole recording (16 kHz mono float) -> (n_frames, 1024), block hop of 5 frames."""
        n = -(-len(audio) // 640)
        ch = SlidingWindowChunker(*self.chunk)
        wins = ch.push(audio) + ch.flush(n)
        return np.concatenate([self.window(w) for w in wins], 0)[:n]

    def features_per_frame(self, audio: np.ndarray, position: int = 4) -> np.ndarray:
        """Hop of one frame: every frame is taken from the same position of its own
        window (``position`` 4 = last valid slot = least look-ahead, 85 ms)."""
        p, v, f = self.chunk
        n = -(-len(audio) // 640)
        left = (p + position) * 640
        right = (v - 1 - position + f) * 640 + 80
        pad = np.concatenate([np.zeros(left, np.float32), audio.astype(np.float32),
                              np.zeros(right + 640, np.float32)])
        win = (p + v + f) * 640 + 80
        return np.stack([self.window(pad[k * 640:k * 640 + win], slice(position, position + 1))[0]
                         for k in range(n)])
