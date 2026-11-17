"""Local stand-in for the GPU worker, for browser playback tests (no GPU, no model).

Serves the real FastAPI app and a built frontend, with an engine that reproduces the
*timing* of the real one: frames are produced in groups of five (one speech-encoder
block), each taking ``render_ms`` to "render", optionally with extra random delay to
imitate network jitter. Every frame shows its own index, so a recording can be checked
for skipped or repeated frames.

    python -m evaluation.benchmarks.fake_server --dist frontend/dist --port 8765
    python -m evaluation.benchmarks.fake_server --dist web/dist/client --diagnostics frontend/dist --port 8765
"""
from __future__ import annotations

import argparse
import random
import threading
import time

import numpy as np

from backend.api.app import create_app
from backend.streaming import protocol as P
from emostream.audio import SampleClock, frame_time
from emostream.constants import EMOTIONS
from emostream.engine.emotion import EmotionTimeline
from emostream.engine.session import Frame
from emostream.safety import Watermark


class BurstSession:
    def __init__(self, req, on_close, block: int, lookahead_frames: int, render_ms: float, jitter_ms: float,
                 clip=None):
        self.req, self.on_close = req, on_close
        self.clip = clip
        self.pcm = bytearray()
        self.block, self.la, self.render_ms, self.jitter_ms = block, lookahead_frames, render_ms, jitter_ms
        self.clock = SampleClock()
        self.timeline = EmotionTimeline(req.emotion, req.intensity)
        self.out = 0
        self.wm = Watermark()
        self.closed = False
        self.rng = random.Random(0)
        self.lat = []
        self.portrait_info = {"mouth_open": False, "lip_open_ratio": 0.0, "mouth_closed_automatically": False}
        self.algorithmic_delay_ms = [self.la * 40, (self.la + block - 1) * 40]

    def _image(self, k: int) -> np.ndarray:
        import cv2

        n = self.req.size
        if self.clip is not None:
            # real avatar frames (as heavy to compress as the real thing), index in the corner
            img = cv2.resize(self.clip[k % len(self.clip)], (n, n)).copy()
            cv2.putText(img, str(k), (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
            # Loudness of this frame's own 40 ms of audio as a white block (top right), so a
            # recording can be checked for audio-video offset: block and sound must coincide.
            a = np.frombuffer(bytes(self.pcm[k * 1280:(k + 1) * 1280]), "<i2").astype(np.float32) / 32768
            level = float(np.sqrt((a ** 2).mean())) if len(a) else 0.0
            img[8:72, n - 72:n - 8] = int(min(255, level * 2500))
            return self.wm.apply(img)
        img = np.full((n, n, 3), 40, np.uint8)
        x = int((k % 50) / 50 * (n - 40))
        img[:, x:x + 40] = (60, 140, 220)                       # a bar that sweeps once every 2 s
        cv2.putText(img, str(k), (20, n // 2), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 6, cv2.LINE_AA)
        return self.wm.apply(img)

    def _frames(self, upto: int) -> list:
        frames = []
        while self.out < upto:
            time.sleep(self.render_ms / 1000 + (self.rng.random() * self.jitter_ms / 1000 if self.jitter_ms else 0))
            k = self.out
            ready = self.clock.frame_ready_time[k] if k < len(self.clock.frame_ready_time) else time.perf_counter()
            ms = (time.perf_counter() - ready) * 1000
            self.lat.append(ms)
            frames.append(Frame(k, frame_time(k), self._image(k), ms))
            self.out += 1
        return frames

    def push_pcm(self, pcm16: bytes, captured_at=None):
        self.pcm += pcm16
        self.clock.push(len(pcm16) // 2, captured_at)
        # a block is released once its last frame plus the look-ahead has arrived
        ready = ((self.clock.complete_frames - self.la) // self.block) * self.block
        return self._frames(max(ready, self.out))

    def set_emotion(self, emotion, intensity, at_seconds=None):
        at = max(self.clock.total_frames, self.out)
        self.timeline.set(emotion, intensity, at)
        return at

    def end(self):
        self.clock.close()
        return self._frames(self.clock.total_frames)

    def stats(self):
        xs = sorted(self.lat) or [0.0]
        return {"frames": self.out, "frames_dropped": 0, "audio_s": self.clock.seconds, "compute_fps": 1000 / max(self.render_ms, 1),
                "latency": {"n": len(xs), "p50_ms": xs[len(xs) // 2], "p95_ms": xs[int(len(xs) * 0.95)], "max_ms": xs[-1]},
                "stages": {"render": {"ms_per_frame": self.render_ms}, "behaviour": {"ms_per_frame": 2.0}}, "gpu": {}}

    def close(self):
        if not self.closed:
            self.closed = True
            self.on_close()


class BurstProvider:
    def __init__(self, block=5, lookahead_frames=3, render_ms=20.0, jitter_ms=0.0, video=""):
        self.kw = dict(block=block, lookahead_frames=lookahead_frames, render_ms=render_ms, jitter_ms=jitter_ms)
        self.clip = None
        if video:
            import cv2

            cap, frames = cv2.VideoCapture(video), []
            while len(frames) < 250:
                ok, f = cap.read()
                if not ok:
                    break
                h, w = f.shape[:2]
                frames.append(cv2.cvtColor(f[:, w - h:], cv2.COLOR_BGR2RGB))     # right-most square panel
            self.clip = frames + frames[::-1]                                     # loop without a jump
        self.lock = threading.Lock()

    def info(self):
        return {"gpu": "none (timing stand-in)", "renderer": "synthetic", "models": ["emostream"],
                "emotions": list(EMOTIONS), "fps": 25, "sample_rate": 16000, "busy": self.lock.locked(), **self.kw}


    def open_session(self, portrait, req):
        if not self.lock.acquire(blocking=False):
            raise P.ProtocolError("busy", "another session is running")
        return BurstSession(req, self.lock.release, clip=self.clip, **self.kw)

    def render_file(self, portrait, audio, req):
        raise P.ProtocolError("model_unavailable", "the timing stand-in cannot export")


def main():
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default="frontend/dist", help="page served at / (web/dist/client for the product UI)")
    ap.add_argument("--diagnostics", default="", help="diagnostics client served at /diagnostics/ (frontend/dist built with EMOSTREAM_BASE=/diagnostics/)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--block", type=int, default=5)
    ap.add_argument("--lookahead-frames", type=int, default=3)
    ap.add_argument("--render-ms", type=float, default=20.0)
    ap.add_argument("--jitter-ms", type=float, default=0.0)
    ap.add_argument("--video", default="", help="a generated clip to use as frames (realistic bitrate)")
    a = ap.parse_args()
    app = create_app(BurstProvider(a.block, a.lookahead_frames, a.render_ms, a.jitter_ms, a.video), static_dir=a.dist,
                     diagnostics_dir=a.diagnostics or None)
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
