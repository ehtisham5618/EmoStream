"""EmoStream's own behaviour model in the engine, and helpers shared by full-face models."""
from __future__ import annotations

import numpy as np

from ..audio import SlidingWindowChunker
from ..constants import EYE_KEYPOINTS
from .behaviour import DittoBehaviour
from .emotion import EmotionTimeline, one_hot_with_intensity


def eye_mask() -> np.ndarray:
    m = np.zeros((21, 3), dtype=np.float32)
    m[list(EYE_KEYPOINTS)] = 1.0
    return m.reshape(-1)


class BlinkSchedule:
    """Eye-closure offsets on a randomised schedule (a blink every 2.4-4 s), using the
    renderer's 15-frame blink template. Deterministic for a given seed."""

    def __init__(self, template, seed: int = 0, min_gap: int = 60, max_gap: int = 100):
        self.template = None if template is None else np.asarray(template, dtype=np.float32)
        self.rng = np.random.default_rng(seed)
        self.min_gap, self.max_gap = min_gap, max_gap
        self.next_start = int(self.rng.integers(min_gap // 2, max_gap))
        self.frame = 0

    def step(self):
        """Offset (63,) for the current frame, or None when the eyes are open."""
        out = None
        if self.template is not None:
            k = self.frame - self.next_start
            if 0 <= k < len(self.template):
                out = self.template[k]
            elif k >= len(self.template):
                self.next_start = self.frame + int(self.rng.integers(self.min_gap, self.max_gap))
        self.frame += 1
        return out


def absolute_motion(x_s_info: dict, source_deg: np.ndarray, delta: np.ndarray, eye_offset=None, mask=None,
                    exp_gain: float = 1.0, pose_gain: float = 1.0) -> dict:
    """Applies a 69-d motion delta (expression 63, rotation in degrees 3, translation 2,
    scale ratio 1) to a source portrait's motion; returns a complete driving dict."""
    exp = x_s_info["exp"].reshape(1, -1) + exp_gain * delta[None, :63]
    if eye_offset is not None:
        exp = exp + (eye_offset * mask if mask is not None else eye_offset)[None]
    pose = source_deg + pose_gain * delta[63:66]
    t = x_s_info["t"].reshape(1, 3).copy()
    t[0, :2] += pose_gain * delta[66:68]
    scale = x_s_info["scale"].reshape(1, 1) * (1.0 + pose_gain * delta[68])
    return {"kp": x_s_info["kp"], "exp": exp.astype(np.float32),
            "pitch": pose[0:1].astype(np.float32), "yaw": pose[1:2].astype(np.float32),
            "roll": pose[2:3].astype(np.float32), "t": t.astype(np.float32), "scale": scale.astype(np.float32)}


class EmoStreamBehaviour:
    """Streaming HuBERT features -> causal two-branch network (emostream.models.BehaviourNet).

    A frame's motion is available as soon as the speech encoder has produced that
    frame's feature: 85 ms of look-ahead, delivered in blocks of five frames (200 ms).
    """

    absolute = True  # complete motion dicts; the session renders them through the full-face path

    def __init__(self, runtime, avatar, timeline: EmotionTimeline, net, chunk=(3, 5, 2), exp_gain: float = 1.0,
                 pose_gain: float = 1.0, blink: bool = True, seed: int = 0, fade_frames: int = 10):
        self.fade_frames = fade_frames  # emotion transition gate: 10 frames = 400 ms cross-fade
        self.rt, self.avatar, self.timeline = runtime, avatar, timeline
        self.torch = runtime.torch
        self.net = net.to(runtime.device).eval()
        self.chunk = tuple(chunk)
        self.wav2feat = runtime.sdk.wav2feat
        self.chunker = SlidingWindowChunker(*self.chunk)
        self.state = None
        self.exp_gain, self.pose_gain = exp_gain, pose_gain
        self.source_deg = runtime.source_degrees(avatar)
        self.mask = eye_mask()
        self.blinks = BlinkSchedule(runtime.blink_template() if blink else None, seed=seed)
        self.frames_out = 0
        self.last_deltas = []  # kept for motion-space evaluation

    def _run(self, windows, limit=None) -> list[dict]:
        if not windows:
            return []
        feats = np.concatenate([self.wav2feat(w, chunksize=self.chunk) for w in windows], 0)
        if limit is not None:
            feats = feats[:max(0, limit)]
        if len(feats) == 0:
            return []
        torch = self.torch
        emo = np.stack([self.timeline.blended(self.frames_out + i, one_hot_with_intensity, self.fade_frames)
                        for i in range(len(feats))])
        with torch.no_grad():
            out, self.state = self.net(torch.from_numpy(feats.astype(np.float32))[None].to(self.rt.device),
                                       torch.from_numpy(emo)[None].to(self.rt.device), self.state)
        deltas = out[0].float().cpu().numpy()
        self.last_deltas.extend(deltas)
        motions = [absolute_motion(self.avatar.x_s_info, self.source_deg, d, self.blinks.step(), self.mask,
                                   self.exp_gain, self.pose_gain) for d in deltas]
        self.frames_out += len(motions)
        return motions

    def push(self, audio: np.ndarray) -> list[dict]:
        return self._run(self.chunker.push(audio))

    def flush(self, total_frames: int) -> list[dict]:
        return self._run(self.chunker.flush(total_frames), limit=total_frames - self.frames_out)

    @property
    def algorithmic_delay_frames(self) -> tuple[int, int]:
        la = self.chunk[2] + 1
        return la, la + self.chunk[1] - 1


class DittoFullFace(DittoBehaviour):
    """Ditto's motion model applied to the whole face instead of lips and eyes only.

    Converts Ditto's relative motion (d - d0) into a complete driving dict so the session
    renders it through the full-face path. Used to test whether Ditto's emotion condition
    becomes visible once brows and cheeks are allowed to move.
    """

    absolute = True

    def __init__(self, runtime, avatar, timeline, **kw):
        super().__init__(runtime, avatar, timeline, **kw)
        from core.atomic_components.motion_stitch import bin66_to_degree

        self._deg = lambda v: float(np.asarray(bin66_to_degree(v)).reshape(-1)[0])
        self.source_deg = runtime.source_degrees(avatar)
        self.mask = eye_mask()
        self.blinks = BlinkSchedule(runtime.blink_template(), seed=0)

    def _to_absolute(self, d: dict) -> dict:
        d0 = self.rest_pose
        delta = np.zeros(69, dtype=np.float32)
        delta[:63] = (d["exp"] - d0["exp"]).reshape(-1)
        delta[63:66] = [self._deg(d[k]) - self._deg(d0[k]) for k in ("pitch", "yaw", "roll")]
        delta[66:68] = (d["t"] - d0["t"]).reshape(-1)[:2]
        delta[68] = float(d["scale"].reshape(-1)[0] / d0["scale"].reshape(-1)[0]) - 1.0
        delta[:63] *= (1.0 - self.mask)  # eyes come from the blink template, as in Ditto
        return absolute_motion(self.avatar_x_s, self.source_deg, delta, self.blinks.step(), self.mask)

    def push(self, audio):
        return [self._to_absolute(m) for m in super().push(audio)]

    def flush(self, total_frames):
        return [self._to_absolute(m) for m in super().flush(total_frames)]
