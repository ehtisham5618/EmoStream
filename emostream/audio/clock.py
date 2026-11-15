"""Sample-accurate bookkeeping for streamed audio.

Audio arrives in chunks of arbitrary size. Every video frame k covers samples
[k * 640, (k + 1) * 640) at 16 kHz. Nothing here looks at the wall clock except
to record *when* a sample arrived, which the latency metric needs.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..constants import SAMPLE_RATE, SAMPLES_PER_FRAME


def pcm16_to_float(pcm: bytes | np.ndarray) -> np.ndarray:
    """Little-endian signed 16-bit PCM -> float32 in [-1, 1)."""
    if isinstance(pcm, (bytes, bytearray, memoryview)):
        pcm = np.frombuffer(pcm, dtype="<i2")
    return (np.asarray(pcm, dtype=np.int16).astype(np.float32)) / 32768.0


def resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    """Polyphase resampling of a mono float signal to 16 kHz."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:  # (n, channels) -> mono
        audio = audio.mean(axis=1)
    if sr == SAMPLE_RATE:
        return audio
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(int(sr), SAMPLE_RATE)
    return resample_poly(audio, SAMPLE_RATE // g, int(sr) // g).astype(np.float32)


@dataclass
class SampleClock:
    """Tracks how many samples have arrived and when each frame became complete."""

    n_samples: int = 0
    # arrival_time[k] = wall-clock time at which the last sample of frame k arrived
    frame_ready_time: list[float] = field(default_factory=list)

    def push(self, n_new: int, now: float | None = None) -> None:
        if n_new < 0:
            raise ValueError("n_new must be non-negative")
        now = time.perf_counter() if now is None else now
        self.n_samples += n_new
        while len(self.frame_ready_time) < self.complete_frames:
            self.frame_ready_time.append(now)

    @property
    def complete_frames(self) -> int:
        """Frames whose audio has fully arrived."""
        return self.n_samples // SAMPLES_PER_FRAME

    @property
    def total_frames(self) -> int:
        """Frames needed to cover all audio, counting a trailing partial frame."""
        return -(-self.n_samples // SAMPLES_PER_FRAME)

    @property
    def seconds(self) -> float:
        return self.n_samples / SAMPLE_RATE

    def close(self, now: float | None = None) -> None:
        """Marks end of stream: a trailing partial frame counts as ready now."""
        now = time.perf_counter() if now is None else now
        while len(self.frame_ready_time) < self.total_frames:
            self.frame_ready_time.append(now)


def frame_time(frame_index: int) -> float:
    """Presentation time in seconds of the start of a frame."""
    return frame_index * SAMPLES_PER_FRAME / SAMPLE_RATE


def frame_of_sample(sample_index: int) -> int:
    return sample_index // SAMPLES_PER_FRAME


class SlidingWindowChunker:
    """Cuts a stream into overlapping fixed windows, as a streaming encoder needs.

    With ``past`` frames of left context, ``valid`` output frames and ``future``
    frames of look-ahead, each window covers ``(past + valid + future) * 640 + extra``
    samples and the stream advances by ``valid`` frames. The stream is left-padded
    with ``past`` frames of silence so the first window yields frames 0..valid-1.
    """

    def __init__(self, past: int = 3, valid: int = 5, future: int = 2, extra_samples: int = 80):
        self.past, self.valid, self.future = past, valid, future
        self.window = (past + valid + future) * SAMPLES_PER_FRAME + extra_samples
        self.hop = valid * SAMPLES_PER_FRAME
        self._buf = np.zeros(past * SAMPLES_PER_FRAME, dtype=np.float32)
        self._pos = 0
        self.frames_emitted = 0

    @property
    def lookahead_samples(self) -> int:
        """Samples beyond the end of the valid block that a window needs."""
        return self.window - (self.past + self.valid) * SAMPLES_PER_FRAME

    def push(self, audio: np.ndarray) -> list[np.ndarray]:
        self._buf = np.concatenate([self._buf[self._pos:], np.asarray(audio, dtype=np.float32)])
        self._pos = 0
        out = []
        while len(self._buf) - self._pos >= self.window:
            out.append(self._buf[self._pos:self._pos + self.window])
            self._pos += self.hop
            self.frames_emitted += self.valid
        return out

    def flush(self, total_frames: int) -> list[np.ndarray]:
        """Pads with silence until windows covering ``total_frames`` have been emitted."""
        out = []
        while self.frames_emitted < total_frames:
            need = self.window - (len(self._buf) - self._pos)
            if need > 0:
                self._buf = np.concatenate([self._buf, np.zeros(need, dtype=np.float32)])
            out.extend(self.push(np.zeros(0, dtype=np.float32)))
        return out
