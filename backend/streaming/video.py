"""Video encoding and network pacing for live sessions.

A live session used to send every frame as an independent JPEG: about 17-35 kB per frame,
3.4-7 Mbit/s at 25 FPS, over one TCP connection. On a link that cannot carry that, frames
queue inside the connection and the picture falls seconds behind (measured: 6.8 s in a
user session on 16 Nov 2026). Real-time video products send inter-frame compressed video
and adapt it to the link. This module does both for the WebSocket transport:

``H264Encoder``  low-delay H.264 (no B-frames, one packet per frame, Annex B with in-band
                 parameter sets), about a tenth of the JPEG bitrate at the same size.
``SendPacer``    uses the client's acknowledgements to estimate how long frames are queueing
                 in the connection, skips frames *before* encoding when a backlog builds,
                 and lowers / restores the bitrate. Pure logic, no I/O, so it is unit-tested.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

DEFAULT_BITRATE_KBPS = 900
MIN_BITRATE_KBPS = 200
MAX_BITRATE_KBPS = 4000
FLOOR_BITRATE_KBPS = 300          # the pacer never goes below this: lower looks worse than skipping


def h264_available() -> bool:
    try:
        import av

        av.codec.Codec("libx264", "w")
        return True
    except Exception:  # noqa: BLE001
        return False


class H264Encoder:
    def __init__(self, size: int, bitrate_kbps: int = DEFAULT_BITRATE_KBPS, fps: int = 25, gop_seconds: float = 2.0):
        self.size, self.fps, self.gop = size, fps, int(round(fps * gop_seconds))
        self.bitrate_kbps = 0
        self._ctx = None
        self._pts = 0
        self._force_key = False
        self.set_bitrate(bitrate_kbps)

    def set_bitrate(self, kbps: int) -> None:
        """Changing the rate restarts the stream; the next frame is a key frame."""
        import av

        kbps = int(max(MIN_BITRATE_KBPS, min(MAX_BITRATE_KBPS, kbps)))
        if kbps == self.bitrate_kbps and self._ctx is not None:
            return
        c = av.CodecContext.create("libx264", "w")
        c.width = c.height = self.size
        c.pix_fmt = "yuv420p"
        c.time_base = Fraction(1, self.fps)
        c.framerate = Fraction(self.fps, 1)
        c.bit_rate = kbps * 1000
        c.options = {
            "preset": "veryfast", "tune": "zerolatency", "profile": "baseline", "bf": "0", "g": str(self.gop),
            # A small rate buffer keeps single frames from bursting far above the target.
            "x264-params": f"vbv-maxrate={kbps}:vbv-bufsize={max(kbps // 2, 100)}:keyint={self.gop}:"
                           f"min-keyint={self.gop}:scenecut=0:repeat-headers=1:aud=0",
        }
        self._ctx = c
        self.bitrate_kbps = kbps

    def request_key_frame(self) -> None:
        self._force_key = True

    def encode(self, rgb: np.ndarray) -> tuple[bytes, bool]:
        """One RGB frame in, one Annex-B access unit out (bytes, is_key_frame)."""
        import av

        frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
        frame.pts = self._pts
        self._pts += 1
        if self._force_key:
            self._force_key = False
            try:
                from av.video.frame import PictureType

                frame.pict_type = PictureType.I
            except Exception:  # noqa: BLE001  (older PyAV takes the letter)
                frame.pict_type = "I"
        data, key = b"", False
        for packet in self._ctx.encode(frame):
            data += bytes(packet)
            key = key or bool(packet.is_keyframe)
        return data, key


@dataclass
class SendPacer:
    """Decides, frame by frame, whether to send, from how far the client is behind.

    The client reports how many frames it has received (about five times a second). The
    time between sending a frame and hearing that it arrived is one network round trip on
    a healthy link; the smallest value seen recently is taken as that baseline. When the
    oldest unconfirmed frame is much older than the baseline, frames are queueing in the
    connection: sending more would only add delay, so frames are skipped before encoding
    and the bitrate is lowered. A client that never acknowledges is never paced.
    """
    bitrate_kbps: int = DEFAULT_BITRATE_KBPS
    max_bitrate_kbps: int = DEFAULT_BITRATE_KBPS
    high_ms: float = 500.0         # queueing delay at which frames start being skipped
    low_ms: float = 150.0          # queueing delay at which normal sending resumes
    ack_interval_ms: float = 200.0  # how often the client reports; not counted as delay
    blind_ms: float = 2500.0       # before any frame is confirmed: age that counts as a stall
    keepalive_every: int = 6       # while skipping, still send every n-th frame
    recover_seconds: float = 4.0   # clean time before the bitrate is raised again
    sent: int = 0
    acked: int = 0                 # frames the client has confirmed (count, not index)
    skipped: int = 0
    congestion_events: int = 0
    skipping: bool = False
    _send_times: deque = field(default_factory=deque)    # time each unconfirmed frame was sent
    _delays: list = field(default_factory=list)          # (time, send -> confirmation delay)
    _since_keepalive: int = 0
    _last_event: float | None = None
    _have_ack: bool = False

    def on_ack(self, frames_received: int, now: float) -> None:
        self._have_ack = True
        n = min(frames_received, self.sent)
        sent_at = None
        while self.acked < n and self._send_times:
            sent_at = self._send_times.popleft()
            self.acked += 1
        if sent_at is not None:
            self._delays.append((now, now - sent_at))
        while self._delays and now - self._delays[0][0] > 10.0 and len(self._delays) > 1:
            self._delays.pop(0)

    @property
    def in_flight(self) -> int:
        return self.sent - self.acked

    def backlog_ms(self, now: float) -> float:
        """Estimated time frames are spending queued in the connection."""
        if not self._have_ack or not self._send_times:
            return 0.0
        age = (now - self._send_times[0]) * 1000
        if not self._delays:
            return max(0.0, age - self.blind_ms)
        baseline = min(d for _, d in self._delays) * 1000
        return max(0.0, age - baseline - self.ack_interval_ms)

    def decide(self, now: float) -> bool:
        """True: encode and send this frame. False: skip it (never encoded)."""
        if self._last_event is None:
            self._last_event = now
        backlog = self.backlog_ms(now)
        if not self.skipping and backlog >= self.high_ms:
            self.skipping = True
            self.congestion_events += 1
            self._last_event = now
            self.bitrate_kbps = max(FLOOR_BITRATE_KBPS, int(self.bitrate_kbps * 0.85))
        elif self.skipping and backlog <= self.low_ms:
            self.skipping = False
            self._last_event = now
        elif (not self.skipping and self.bitrate_kbps < self.max_bitrate_kbps
              and now - self._last_event >= self.recover_seconds):
            self.bitrate_kbps = min(self.max_bitrate_kbps, int(self.bitrate_kbps * 1.25) + 1)
            self._last_event = now
        if self.skipping:
            self._since_keepalive += 1
            if self._since_keepalive < self.keepalive_every:
                self.skipped += 1
                return False
        self._since_keepalive = 0
        self.record_sent(now)
        return True

    def record_sent(self, now: float) -> None:
        self.sent += 1
        self._send_times.append(now)


class ArrivalJitter:
    """How unevenly audio reaches the server: arrival time minus audio time, relative to
    the best case seen. Large values mean the uplink is delivering in bursts."""

    def __init__(self, window_s: float = 5.0):
        self.window_s = window_s
        self._best: float | None = None
        self._recent: list[tuple[float, float]] = []

    def add(self, arrival: float, audio_seconds_after: float) -> None:
        d = arrival - audio_seconds_after
        self._best = d if self._best is None else min(self._best, d)
        self._recent.append((arrival, d))
        while self._recent and arrival - self._recent[0][0] > self.window_s:
            self._recent.pop(0)

    def summary(self) -> dict:
        if not self._recent or self._best is None:
            return {"lag_p95_ms": None, "lag_max_ms": None}
        xs = sorted((d - self._best) * 1000 for _, d in self._recent)
        return {"lag_p95_ms": round(xs[min(len(xs) - 1, int(0.95 * len(xs)))], 1), "lag_max_ms": round(xs[-1], 1)}
