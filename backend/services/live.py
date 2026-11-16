"""Live-session service: the boundary between the web layer and the GPU engine.

The web layer only sees ``EngineProvider`` and ``LiveSession``. The real provider
(``GpuEngineProvider``) needs the GPU runtime; tests use an in-memory fake, so the
API can be exercised without a GPU.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from typing import Protocol

import numpy as np

from emostream.audio import pcm16_to_float, resample_to_16k
from emostream.constants import EMOTIONS, FPS, SAMPLE_RATE

from ..streaming.protocol import MAX_SESSION_SECONDS, ProtocolError, StartRequest


class LiveSession(Protocol):
    def push_pcm(self, pcm16: bytes, captured_at: float | None = None) -> list: ...
    def set_emotion(self, emotion: str, intensity: float, at_seconds: float | None = None) -> int: ...
    def end(self) -> list: ...
    def stats(self) -> dict: ...
    def close(self) -> None: ...


class EngineProvider(Protocol):
    def info(self) -> dict: ...
    def open_session(self, portrait: bytes, req: StartRequest, hop: int | None = None) -> LiveSession: ...


class EngineSessionAdapter:
    """Wraps an ``emostream.engine.session.AvatarSession`` for the web layer:
    PCM decoding, resampling to 16 kHz, the session time limit, and release of the
    single-session slot."""

    def __init__(self, session, sample_rate: int, on_close=None):
        self.session = session
        self.sample_rate = sample_rate
        self._on_close = on_close
        self._closed = False

    def push_pcm(self, pcm16: bytes, captured_at: float | None = None) -> list:
        audio = pcm16_to_float(pcm16)
        if self.sample_rate != SAMPLE_RATE:
            # Chunk-wise polyphase resampling. The browser client records at 16 kHz, so this
            # path is a fallback; it has small edge effects at chunk boundaries.
            audio = resample_to_16k(audio, self.sample_rate)
        if self.session.clock.seconds + len(audio) / SAMPLE_RATE > MAX_SESSION_SECONDS:
            raise ProtocolError("session_too_long", f"sessions are limited to {MAX_SESSION_SECONDS // 60} minutes")
        return self.session.push_audio(audio, captured_at=captured_at)

    def set_emotion(self, emotion: str, intensity: float, at_seconds: float | None = None) -> int:
        return self.session.set_emotion(emotion, intensity, at_seconds=at_seconds)

    def end(self) -> list:
        return self.session.end()

    def stats(self) -> dict:
        return self.session.stats()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._on_close:
                self._on_close()


class GpuEngineProvider:
    """Real engine. One live session at a time per GPU worker."""

    def __init__(self, checkpoints: str, emostream_checkpoint: str | None, max_latency_ms: float | None = 450.0,
                 tensorrt: bool = False, emotion_gain: float = 1.0, hop: int = 1):
        import torch

        from emostream.engine.runtime import Runtime

        self.torch = torch
        self.rt = Runtime(checkpoints, tensorrt=tensorrt)
        self.renderer = "tensorrt_fp16" if tensorrt else "pytorch_fp16"
        self.net = None
        if emostream_checkpoint and os.path.exists(emostream_checkpoint):
            from emostream.models import BehaviourNet

            self.net = BehaviourNet.load(torch.load(emostream_checkpoint, map_location="cpu", weights_only=False))
        self.max_latency_ms = max_latency_ms
        self.emotion_gain = emotion_gain
        # Live sessions: hop 1 (one frame per encoder window) gives evenly spaced frames and
        # the lowest delay; hop 5 (as in training) is slightly more accurate and is used for
        # exports and on GPUs that cannot afford five encoder passes per block.
        self.hop = hop
        self._busy = threading.Lock()
        self.started = time.time()

    def warm_up(self, portrait_path: str, seconds: float = 2.0) -> dict:
        """Runs one short throw-away session so that the first real one does not pay for
        lazy initialisation (face models, speech encoder, renderer, first CUDA calls).
        Returns timings; never raises (a failed warm-up only means a slower first session)."""
        t0 = time.perf_counter()
        out = {"ok": False}
        try:
            with open(portrait_path, "rb") as f:
                portrait = f.read()
            adapter = self.open_session(portrait, StartRequest(SAMPLE_RATE, "neutral", 0.5,
                                                               "emostream" if self.net is not None else "ditto",
                                                               512, 80))
            out["register_s"] = round(time.perf_counter() - t0, 2)
            try:
                rng = np.random.default_rng(0)
                pcm = (rng.standard_normal(int(SAMPLE_RATE * 0.08)) * 800).astype("<i2").tobytes()
                first, frames = None, 0
                t1 = time.perf_counter()
                for _ in range(int(seconds / 0.08)):
                    got = adapter.push_pcm(pcm, time.perf_counter())
                    frames += len(got)
                    if got and first is None:
                        first = round(time.perf_counter() - t1, 2)
                out.update(ok=True, first_frame_s=first, frames=frames)
            finally:
                adapter.close()
        except Exception as e:  # noqa: BLE001
            out["error"] = f"{type(e).__name__}: {e}"
        out["total_s"] = round(time.perf_counter() - t0, 2)
        self.warm = out
        return out

    def info(self) -> dict:
        return {
            "warm_up": getattr(self, "warm", None),
            "gpu": self.torch.cuda.get_device_name(0), "renderer": self.renderer,
            "models": (["emostream"] if self.net is not None else []) + ["ditto"],
            "emotions": list(EMOTIONS), "fps": FPS, "sample_rate": SAMPLE_RATE,
            "busy": self._busy.locked(), "max_session_seconds": MAX_SESSION_SECONDS,
            "emostream_parameters": self.net.n_parameters() if self.net is not None else None,
            "emostream_lookahead_frames": int(getattr(self.net.cfg, "lookahead", 0)) if self.net is not None else None,
            "emotion_gain": self.emotion_gain, "live_hop": self.hop,
        }

    def open_session(self, portrait: bytes, req: StartRequest, hop: int | None = None) -> LiveSession:
        from emostream.engine.behaviour import DittoBehaviour
        from emostream.engine.session import AvatarSession

        if req.model == "emostream" and self.net is None:
            raise ProtocolError("model_unavailable", "the EmoStream model is not loaded on this worker")
        if not self._busy.acquire(blocking=False):
            raise ProtocolError("busy", "another session is running on this worker; try again shortly")
        try:
            # The portrait is written to a private temporary file only for the image
            # decoder and is deleted immediately; nothing is stored after the session.
            with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as f:
                f.write(portrait)
                path = f.name
            try:
                avatar = self.rt.register(path)
            except Exception as e:  # noqa: BLE001
                raise ProtocolError("no_face", "no usable face was found in the portrait") from e
            finally:
                os.remove(path)

            def factory(runtime, av, timeline):
                if req.model == "emostream":
                    from emostream.engine.behaviour_emostream import EmoStreamBehaviour

                    return EmoStreamBehaviour(runtime, av, timeline, self.net, hop=hop or self.hop,
                                              emotion_gain=self.emotion_gain)
                return DittoBehaviour(runtime, av, timeline, sampling_timesteps=10, valid_frames=10)

            session = AvatarSession(self.rt, avatar, factory, emotion=req.emotion, intensity=req.intensity,
                                    size=req.size, portrait_consent=True, audio_consent=True,
                                    max_latency_ms=self.max_latency_ms)
            adapter = EngineSessionAdapter(session, req.sample_rate, on_close=self._busy.release)
            adapter.portrait_info = {
                "mouth_open": bool(getattr(avatar, "mouth_open", False)),
                "lip_open_ratio": round(float(getattr(avatar, "lip_ratio", 0.0)), 4),
                "mouth_closed_automatically": getattr(avatar, "lip_delta", None) is not None,
            }
            lo, hi = session.behaviour.algorithmic_delay_frames
            adapter.algorithmic_delay_ms = [lo * 40, hi * 40]
            return adapter
        except BaseException:
            self._busy.release()
            raise


    def render_file(self, portrait: bytes, audio_file: bytes, req: StartRequest, max_seconds: float = 180.0):
        """Offline export: any audio file ffmpeg can read -> watermarked H.264/AAC MP4 bytes.
        All temporary files are removed before returning."""
        import shutil
        import subprocess

        import imageio

        from emostream.engine.session import stream_file

        work = tempfile.mkdtemp(prefix="export_")
        adapter = None
        try:
            src = os.path.join(work, "audio.in")
            with open(src, "wb") as f:
                f.write(audio_file)
            wav = os.path.join(work, "audio.wav")
            r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar",
                                str(SAMPLE_RATE), "-t", str(max_seconds), "-c:a", "pcm_s16le", wav],
                               capture_output=True)
            if r.returncode != 0:
                raise ProtocolError("bad_audio", "the audio file could not be decoded")
            import soundfile as sf

            audio, _ = sf.read(wav, dtype="float32")
            if len(audio) < SAMPLE_RATE // 4:
                raise ProtocolError("bad_audio", "the audio is shorter than a quarter of a second")
            adapter = self.open_session(portrait, StartRequest(SAMPLE_RATE, req.emotion, req.intensity, req.model,
                                                               req.size, req.jpeg_quality), hop=5)
            adapter.session.max_latency_ms = None  # never skip frames in an export
            silent = os.path.join(work, "video.mp4")
            writer = imageio.get_writer(silent, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
            for fr in stream_file(adapter.session, audio, chunk_ms=200, paced=False):
                writer.append_data(fr.rgb)
            writer.close()
            out = os.path.join(work, "out.mp4")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", silent, "-i", wav, "-map", "0:v", "-map",
                            "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart", out],
                           check=True)
            with open(out, "rb") as f:
                return f.read(), adapter.stats()
        finally:
            if adapter is not None:
                adapter.close()
            shutil.rmtree(work, ignore_errors=True)


def encode_jpeg(rgb: np.ndarray, quality: int) -> bytes:
    import cv2

    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()
