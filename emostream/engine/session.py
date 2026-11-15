"""One streaming avatar session: audio chunks in, timestamped frames out."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..audio import SampleClock, frame_time
from ..constants import FPS, SAMPLE_RATE, SAMPLES_PER_FRAME
from ..safety import Watermark, require_consent
from ..telemetry import LatencyTracker, StageTimer
from .emotion import EmotionTimeline


@dataclass
class Frame:
    index: int          # frame k covers audio samples [k * 640, (k + 1) * 640)
    time_s: float       # presentation time of the frame start
    rgb: np.ndarray | None  # HxWx3 uint8, watermarked; None when the frame was skipped to catch up
    latency_ms: float   # arrival of the frame's last audio sample -> frame handed out


class AvatarSession:
    """Drives a behaviour model and the renderer for one portrait.

    ``push_audio`` accepts mono float32 audio at 16 kHz in chunks of any size and
    returns the frames that became available. ``end`` flushes the tail. Frame
    timestamps come from sample counts only.
    """

    def __init__(self, runtime, avatar, behaviour_factory, *, emotion: str = "neutral", intensity: float = 1.0,
                 size: int = 512, full_frame: bool = False, watermark: bool = True,
                 portrait_consent: bool = False, audio_consent: bool = False, motion_filter=None,
                 max_latency_ms: float | None = None):
        require_consent(portrait_consent, audio_consent)
        # Live mode: when a frame is already older than this, skip rendering it (the viewer
        # keeps the previous image) so that delay stays bounded on a GPU that is too slow.
        # At least every third frame is always rendered.
        self.max_latency_ms = max_latency_ms
        self.frames_dropped = 0
        self._since_render = 0
        self.rt = runtime
        self.avatar = avatar
        self.size = size
        self.full_frame = full_frame
        self.timeline = EmotionTimeline(emotion, intensity)
        self.behaviour = behaviour_factory(runtime, avatar, self.timeline)
        self.stitch = runtime.new_stitcher(avatar)
        self.motion_filter = motion_filter  # optional callable(motion, frame_index, timeline) -> motion
        self.clock = SampleClock()
        self.timer = StageTimer()
        self.latency = LatencyTracker()
        self.watermark = Watermark() if watermark else None
        self.frames_out = 0
        self.closed = False
        self.started_at = time.perf_counter()

    # -- control -----------------------------------------------------------------------
    def set_emotion(self, emotion: str, intensity: float = 1.0, at_seconds: float | None = None) -> int:
        """Schedules an emotion change. Without ``at_seconds`` it starts at the end of
        the audio received so far. Returns the frame at which it takes effect; frames
        already generated are not changed."""
        at_frame = self.clock.total_frames if at_seconds is None else int(round(at_seconds * FPS))
        at_frame = max(at_frame, self.frames_out)
        self.timeline.set(emotion, intensity, at_frame)
        return at_frame

    # -- data path ---------------------------------------------------------------------
    def _render(self, motions: list[dict]) -> list[Frame]:
        frames = []
        for m in motions:
            k = self.frames_out
            if self.stitch.d0 is None and getattr(self.behaviour, "rest_pose", None) is not None:
                self.stitch.d0 = self.behaviour.rest_pose
            if self.motion_filter is not None:
                m = self.motion_filter(m, k, self.timeline)
            ready_k = self.clock.frame_ready_time[k] if k < len(self.clock.frame_ready_time) else None
            if (self.max_latency_ms is not None and ready_k is not None and self._since_render < 2
                    and (time.perf_counter() - ready_k) * 1000.0 > self.max_latency_ms):
                self._since_render += 1
                self.frames_dropped += 1
                self.frames_out += 1
                frames.append(Frame(k, frame_time(k), None, float("nan")))
                continue
            self._since_render = 0
            with self.timer.time("stitch"):
                if getattr(self.behaviour, "absolute", False):
                    x_s, x_d = self.rt.keypoints_full_face(self.avatar, m)
                else:
                    x_s, x_d = self.stitch(self.avatar.x_s_info, m)
            with self.timer.time("render"):
                rgb = self.rt.render_keypoints(self.avatar, x_s, x_d, 512 if self.full_frame else self.size)
            with self.timer.time("post"):
                if self.full_frame:
                    rgb = np.ascontiguousarray(self.rt.paste_back(self.avatar, rgb))
                if self.watermark is not None:
                    rgb = self.watermark.apply(rgb)
            ready = self.clock.frame_ready_time[k] if k < len(self.clock.frame_ready_time) else time.perf_counter()
            frames.append(Frame(k, frame_time(k), rgb, self.latency.record(ready)))
            self.frames_out += 1
        return frames

    def push_audio(self, audio: np.ndarray, captured_at: float | None = None) -> list[Frame]:
        """``captured_at`` is the ``time.perf_counter()`` value at which the last sample
        of this chunk was captured; it defaults to now. Passing the true capture time
        keeps the latency metric honest when the engine falls behind real time."""
        if self.closed:
            raise RuntimeError("session already ended")
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        self.clock.push(len(audio), captured_at)
        with self.timer.time("behaviour"):
            motions = self.behaviour.push(audio)
        return self._render(motions)

    def end(self) -> list[Frame]:
        if self.closed:
            return []
        self.closed = True
        self.clock.close()
        with self.timer.time("behaviour"):
            motions = self.behaviour.flush(self.clock.total_frames)
        return self._render(motions)

    # -- reporting ---------------------------------------------------------------------
    def stats(self, skip_frames: int = 0) -> dict:
        n = self.frames_out
        busy = sum(self.timer.total.values())
        return {
            "frames": n,
            "frames_rendered": n - self.frames_dropped,
            "frames_dropped": self.frames_dropped,
            "audio_s": round(self.clock.seconds, 3),
            "expected_frames": self.clock.total_frames,
            "compute_s": round(busy, 3),
            "compute_fps": round(n / busy, 2) if busy > 0 else None,
            "stages": self.timer.summary(n),
            "latency": self.latency.summary(skip=skip_frames),
            "emotion_changes": self.timeline.changes(),
            "gpu": self.rt.gpu_memory(),
        }


def stream_file(session: AvatarSession, audio: np.ndarray, chunk_ms: int = 200, paced: bool = False):
    """Feeds a whole recording through a session in fixed chunks and yields frames.

    ``paced=True`` delivers each chunk at the time a live microphone would (a chunk
    is available once its last sample has been captured), which is what makes the
    latency numbers meaningful. ``paced=False`` pushes as fast as possible.
    """
    step = max(1, int(SAMPLE_RATE * chunk_ms / 1000))
    t0 = time.perf_counter()
    for i in range(0, len(audio), step):
        chunk = audio[i:i + step]
        if paced:
            due = t0 + (i + len(chunk)) / SAMPLE_RATE
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            yield from session.push_audio(chunk, captured_at=due)
        else:
            yield from session.push_audio(chunk)
    yield from session.end()


__all__ = ["AvatarSession", "Frame", "stream_file", "SAMPLES_PER_FRAME"]
