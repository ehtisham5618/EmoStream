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
                    exp_gain: float = 1.0, pose_gain: float = 1.0, base_offset=None) -> dict:
    """Applies a 69-d motion delta (expression 63, rotation in degrees 3, translation 2,
    scale ratio 1) to a source portrait's motion; returns a complete driving dict.
    ``base_offset`` (63,) is added to the source expression first, e.g. the lip-closing
    offset for a portrait whose mouth is open."""
    exp = x_s_info["exp"].reshape(1, -1) + exp_gain * delta[None, :63]
    if base_offset is not None:
        exp = exp + base_offset[None]
    if eye_offset is not None:
        exp = exp + (eye_offset * mask if mask is not None else eye_offset)[None]
    pose = source_deg + pose_gain * delta[63:66]
    t = x_s_info["t"].reshape(1, 3).copy()
    t[0, :2] += pose_gain * delta[66:68]
    scale = x_s_info["scale"].reshape(1, 1) * (1.0 + pose_gain * delta[68])
    return {"kp": x_s_info["kp"], "exp": exp.astype(np.float32),
            "pitch": pose[0:1].astype(np.float32), "yaw": pose[1:2].astype(np.float32),
            "roll": pose[2:3].astype(np.float32), "t": t.astype(np.float32), "scale": scale.astype(np.float32)}


_WAVLM_CACHE: dict = {}


def wavlm_extractor(config: dict | None, device: str):
    """One WavLM encoder per worker and configuration (loading takes about a second)."""
    from ..audio.wavlm import WavLMFeatures

    cfg = config or {}
    key = (cfg.get("layer", 6), cfg.get("past_samples", 16000), cfg.get("future_frames", 2), str(device))
    if key not in _WAVLM_CACHE:
        _WAVLM_CACHE[key] = WavLMFeatures(layer=key[0], past_s=key[1] / 16000, future_frames=key[2], device=device)
    return _WAVLM_CACHE[key]


class EmoStreamBehaviour:
    """Streaming HuBERT features -> causal two-branch network (emostream.models.BehaviourNet).

    ``hop`` is how many frames the speech encoder advances per window:

    * ``hop=5`` (how the features were computed for training): one window yields five
      frames, so frames come out in groups of five every 200 ms and wait 85-245 ms.
    * ``hop=1``: one window per frame, each frame taken from slot ``slot`` (0-4) of the
      five valid positions of its own window. Frames come out one at a time, evenly.
      Slot 4 (default) waits least: 85 ms of encoder look-ahead. Training features were
      cut in blocks, so a frame's feature came from any slot; lower slots give the encoder
      more future audio (slot 0: 245 ms) and measured closer to training accuracy
      (docs/evaluation/data/feature_position_check.json). Five times the encoder work.

    A model trained with ``lookahead`` L additionally waits for L more feature frames
    (L x 40 ms) before it emits a frame.
    """

    absolute = True  # complete motion dicts; the session renders them through the full-face path

    def __init__(self, runtime, avatar, timeline: EmotionTimeline, net, chunk=(3, 5, 2), exp_gain: float = 1.0,
                 pose_gain: float = 1.0, blink: bool = True, seed: int = 0, fade_frames: int = 10, hop: int = 5,
                 lip_close=None, emotion_gain: float = 1.0, slot: int = 4):
        assert hop in (1, 5), "hop must be 1 (per frame) or 5 (per block)"
        assert 0 <= slot <= 4, "slot must be 0..4"
        self.slot = slot
        self.fade_frames = fade_frames  # emotion transition gate: 10 frames = 400 ms cross-fade
        self.rt, self.avatar, self.timeline = runtime, avatar, timeline
        self.torch = runtime.torch
        self.net = net.to(runtime.device).eval()
        self.chunk = tuple(chunk)
        self.hop = hop
        self.lookahead = int(getattr(net.cfg, "lookahead", 0))
        self.features = getattr(net.cfg, "features", "ditto_hubert")
        self.wavlm = None
        if self.features == "wavlm":
            # Speech features from WavLM, one per frame, exactly as computed for training.
            from ..audio.wavlm import WavLMStream

            self.wavlm = WavLMStream(wavlm_extractor(getattr(net.cfg, "feature_config", None), runtime.device))
        self.wav2feat = runtime.sdk.wav2feat
        p, v, f = self.chunk
        # hop 1: slide the same 10-frame window by one frame; the frame sits at valid slot
        # ``slot``, i.e. after p + slot frames of past and before (v - 1 - slot) + f frames of future
        self.chunker = (SlidingWindowChunker(p, v, f) if hop == 5
                        else SlidingWindowChunker(p + slot, 1, v - 1 - slot + f))
        self.state = None
        self.exp_gain, self.pose_gain = exp_gain, pose_gain
        # Scale of the emotion branch's contribution. 1.0 is what the model learned; the
        # articulation branch is never scaled by it.
        self.emotion_gain = emotion_gain
        self.source_deg = runtime.source_degrees(avatar)
        self.mask = eye_mask()
        self.blinks = BlinkSchedule(runtime.blink_template() if blink else None, seed=seed)
        self.lip_close = lip_close   # (63,) keypoint offset that closes an open-mouthed portrait, or None
        self.frames_out = 0
        self.feats = None            # features not yet consumed by the network
        self.last_deltas = []        # kept for motion-space evaluation

    def _features(self, windows) -> None:
        if not windows:
            return
        if self.hop == 5:
            new = [self.wav2feat(w, chunksize=self.chunk) for w in windows]
        else:
            new = [self.wav2feat(w, chunksize=self.chunk)[self.slot:self.slot + 1] for w in windows]
        new = np.concatenate(new, 0).astype(np.float32)
        self.feats = new if self.feats is None else np.concatenate([self.feats, new], 0)

    def _emit(self, total_frames=None) -> list[dict]:
        """Runs the network on every frame whose (look-ahead shifted) feature is available.
        At the end of a stream the last feature is repeated, as in training."""
        if self.feats is None:
            return []
        L = self.lookahead
        if total_frames is None:
            n = len(self.feats) - L
            x = self.feats[L:L + n] if n > 0 else None
        else:
            n = max(0, total_frames - self.frames_out)
            x = None
            if n > 0 and len(self.feats):
                pad = np.repeat(self.feats[-1:], max(0, L + n - len(self.feats)), 0)
                x = np.concatenate([self.feats, pad], 0)[L:L + n]
        if x is None or len(x) == 0:
            return []
        self.feats = self.feats[len(x):]
        torch = self.torch
        emo = np.stack([self.timeline.blended(self.frames_out + i, one_hot_with_intensity, self.fade_frames)
                        for i in range(len(x))])
        with torch.no_grad():
            out, self.state, parts = self.net(torch.from_numpy(x)[None].to(self.rt.device),
                                              torch.from_numpy(emo)[None].to(self.rt.device), self.state,
                                              return_parts=True)
            if self.emotion_gain != 1.0:
                out = parts["art"] + self.emotion_gain * parts["emo"]
        deltas = out[0].float().cpu().numpy()
        self.last_deltas.extend(deltas)
        motions = [absolute_motion(self.avatar.x_s_info, self.source_deg, d, self.blinks.step(), self.mask,
                                   self.exp_gain, self.pose_gain, self.lip_close) for d in deltas]
        self.frames_out += len(motions)
        return motions

    def _add(self, new: np.ndarray) -> None:
        if len(new):
            new = new.astype(np.float32)
            self.feats = new if self.feats is None else np.concatenate([self.feats, new], 0)

    def push(self, audio: np.ndarray) -> list[dict]:
        if self.wavlm is not None:
            self._add(self.wavlm.push(audio))
        else:
            self._features(self.chunker.push(audio))
        return self._emit()

    def flush(self, total_frames: int) -> list[dict]:
        if self.wavlm is not None:
            self._add(self.wavlm.flush(total_frames))
        else:
            self._features(self.chunker.flush(total_frames))
        return self._emit(total_frames)

    @property
    def algorithmic_delay_frames(self) -> tuple[int, int]:
        if self.wavlm is not None:
            la = self.wavlm.delay_frames + 1 + self.lookahead
            return (la, la)
        la = self.chunk[2] + 1 + self.lookahead
        return (la + 4 - self.slot,) * 2 if self.hop == 1 else (la, la + self.chunk[1] - 1)


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


class OracleBehaviour:
    """Replays known motion deltas (e.g. extracted from the real video of the same clip).

    This is not a model. It isolates the renderer: if real motion driven through the
    renderer reproduces the real video's mouth and jaw movement, then any shortfall in a
    model's output is the model's, not the renderer's.
    """

    absolute = True

    def __init__(self, runtime, avatar, timeline, deltas: np.ndarray, blink: bool = False):
        self.rt, self.avatar = runtime, avatar
        self.deltas = np.asarray(deltas, dtype=np.float32)
        self.source_deg = runtime.source_degrees(avatar)
        self.mask = eye_mask()
        self.blinks = BlinkSchedule(runtime.blink_template() if blink else None)
        self.samples = 0
        self.frames_out = 0
        self.last_deltas = []

    def _emit(self, upto: int) -> list[dict]:
        out = []
        while self.frames_out < upto:
            d = self.deltas[min(self.frames_out, len(self.deltas) - 1)]
            self.last_deltas.append(d)
            out.append(absolute_motion(self.avatar.x_s_info, self.source_deg, d, self.blinks.step(), self.mask))
            self.frames_out += 1
        return out

    def push(self, audio: np.ndarray) -> list[dict]:
        self.samples += len(audio)
        return self._emit(self.samples // 640)

    def flush(self, total_frames: int) -> list[dict]:
        return self._emit(total_frames)

    @property
    def algorithmic_delay_frames(self) -> tuple[int, int]:
        return 0, 0
