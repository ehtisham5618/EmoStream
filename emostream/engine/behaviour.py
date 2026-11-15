"""Behaviour models: streamed 16 kHz audio (+ emotion) -> per-frame motion.

A behaviour model is anything with

    push(audio: float32[n]) -> list[motion]     # zero or more new frames, in order
    flush(total_frames: int) -> list[motion]    # end of stream: emit what remains

where ``motion`` is a LivePortrait driving dict (``exp`` (1, 63), ``pitch``/``yaw``/
``roll``, ``t`` (1, 3), ``scale`` (1, 1)). The renderer does not care which model
produced it, so models can be swapped and compared on identical inputs.
"""
from __future__ import annotations

import copy

import numpy as np

from ..audio import SlidingWindowChunker
from .emotion import EmotionTimeline, ditto_emotion_vector


class DittoBehaviour:
    """Pretrained baseline: Ditto's streaming HuBERT encoder and motion-diffusion model.

    A synchronous re-implementation of the audio->motion part of Ditto's
    ``stream_pipeline_online.py`` (no worker threads), with the emotion condition
    taken per frame from an :class:`EmotionTimeline`.

    Algorithmic delay, in frames: the encoder needs ``chunk[2]`` frames (+5 ms) of
    look-ahead; the motion model emits a block of ``valid`` frames only after the
    *next* block of ``valid`` frames has arrived, because consecutive windows are
    cross-faded over one block. With the released online setting (valid = 10) the
    last frame of a block therefore waits about 0.4 s and the first about 0.8 s.
    """

    def __init__(self, runtime, avatar, timeline: EmotionTimeline, sampling_timesteps: int = 10,
                 valid_frames: int = 10, chunk=(3, 5, 2), seed: int | None = 0):
        sdk = runtime.sdk
        d = runtime.defaults
        self.rt = runtime
        self.avatar_x_s = avatar.x_s_info
        self.timeline = timeline
        self.chunk = tuple(chunk)
        self.wav2feat = sdk.wav2feat
        self.cond = copy.copy(sdk.condition_handler)
        self.a2m = copy.copy(sdk.audio2motion)
        if seed is not None:
            runtime.torch.manual_seed(seed)
            np.random.seed(seed)

        self.seq = self.a2m.lmdm.seq_frames
        overlap = self.seq - int(valid_frames)
        self.cond.setup(avatar.source_info, 4, eye_f0_mode=d.get("eye_f0_mode", False), ch_info=d.get("ch_info"))
        self.a2m.setup(
            self.cond.x_s_info_0, overlap_v2=overlap, fix_kp_cond=d.get("fix_kp_cond", 0),
            fix_kp_cond_dim=d.get("fix_kp_cond_dim"), sampling_timesteps=sampling_timesteps,
            online_mode=True, v_min_max_for_clip=d.get("v_min_max_for_clip"), smo_k_d=d.get("smo_k_d", 3),
        )
        self.valid = self.a2m.valid_clip_len
        self.chunker = SlidingWindowChunker(*self.chunk)

        # Feature buffer starts with `overlap` frames computed from silence.
        self.feat = self.wav2feat.wav2feat(np.zeros((overlap * 640,), dtype=np.float32), sr=16000,
                                           chunksize=self.chunk)
        assert len(self.feat) == overlap, len(self.feat)
        self.cond_idx_start = -overlap
        self.pending = np.zeros((0, self.feat.shape[1]), dtype=np.float32)
        self.local_idx = 0
        self.global_idx = 0
        self.res = None
        self.valid_start = None
        self.rest_pose = None      # first generated frame, used as the relative-motion origin
        self.frames_out = 0

    # -- helpers ---------------------------------------------------------------------
    def _emotion_seq(self, start_frame: int, n: int) -> np.ndarray:
        return np.stack([ditto_emotion_vector(*self.timeline.at(max(i, 0))) for i in range(start_frame, start_frame + n)])

    def _run(self, is_end: bool) -> list[dict]:
        out: list[dict] = []
        if not is_end and len(self.pending) < self.valid:
            return out
        self.feat = np.concatenate([self.feat, self.pending], 0)
        self.pending = self.pending[:0]
        while True:
            aud = self.feat[self.local_idx:self.local_idx + self.seq]
            real_valid = self.valid
            if len(aud) == 0:
                break
            if len(aud) < self.seq:
                if not is_end:
                    break
                real_valid = len(aud)
                aud = np.concatenate([aud, np.stack([aud[-1]] * (self.seq - len(aud)), 0)], 0)
            g = self.global_idx + self.cond_idx_start
            cond = self.cond(aud, g, emo=self._emotion_seq(g, self.seq))[None]
            self.res = self.a2m(cond, self.res)
            if self.valid_start is None:  # first window: establishes the rest pose, emits nothing
                self.valid_start = self.res.shape[1] - self.a2m.fuse_length
                self.rest_pose = self.a2m.cvt_fmt(self.res[0:1])[0]
            else:
                block = self.res[:, self.valid_start:self.valid_start + real_valid]
                out.extend(self.a2m.cvt_fmt(block))
                self.valid_start += real_valid
            self.local_idx += real_valid
            self.global_idx += real_valid
            L = self.res.shape[1]
            if L > self.seq * 2:
                cut = L - self.seq * 2
                self.res = self.res[:, cut:]
                self.valid_start -= cut
            if self.local_idx >= len(self.feat):
                break
        L = len(self.feat)
        if L > self.seq * 2:
            cut = L - self.seq * 2
            self.feat = self.feat[cut:]
            self.local_idx -= cut
        return out

    def _features(self, windows) -> None:
        if windows:
            feats = [self.wav2feat(w, chunksize=self.chunk) for w in windows]
            self.pending = np.concatenate([self.pending, *feats], 0)

    # -- public ----------------------------------------------------------------------
    def push(self, audio: np.ndarray) -> list[dict]:
        self._features(self.chunker.push(audio))
        out = self._run(is_end=False)
        self.frames_out += len(out)
        return out

    def flush(self, total_frames: int) -> list[dict]:
        self._features(self.chunker.flush(total_frames))
        out = self._run(is_end=True)
        out = out[:max(0, total_frames - self.frames_out)]
        self.frames_out += len(out)
        return out

    @property
    def algorithmic_delay_frames(self) -> tuple[int, int]:
        """(min, max) frames a motion frame waits for future audio, excluding compute."""
        la = self.chunk[2] + 1  # encoder look-ahead (2 frames + 80 samples, rounded up)
        return self.valid + la, 2 * self.valid - 1 + la
