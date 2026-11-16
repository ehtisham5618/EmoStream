"""EmoStreamBehaviour streaming logic with a stand-in runtime (no GPU, no weights)."""
import numpy as np
import pytest
import torch

from emostream.engine.behaviour_emostream import EmoStreamBehaviour, absolute_motion
from emostream.engine.emotion import EmotionTimeline
from emostream.models import BehaviourConfig, BehaviourNet
from emostream.training.data import shift_features
from emostream.training.trainer import ccc_loss

D = 16


class FakeSDK:
    """wav2feat returns, for each of the five valid frames of a window, a feature that
    encodes that frame's own audio (its mean), so tests can tell which frame is which."""

    class _W:
        def __call__(self, window, chunksize=(3, 5, 2)):
            p, v, _ = chunksize
            return np.stack([np.full(D, window[(p + k) * 640:(p + k + 1) * 640].mean(), np.float32) for k in range(v)])

    def __init__(self):
        self.wav2feat = self._W()


class FakeRuntime:
    device = "cpu"
    torch = torch

    def __init__(self):
        self.sdk = FakeSDK()

    def source_degrees(self, avatar):
        return np.zeros(3, np.float32)

    def blink_template(self):
        return None


class Avatar:
    x_s_info = {"kp": np.zeros((1, 63), np.float32), "exp": np.zeros((1, 63), np.float32),
                "t": np.zeros((1, 3), np.float32), "scale": np.ones((1, 1), np.float32)}


def make(hop, lookahead=0, seed=0):
    torch.manual_seed(seed)
    net = BehaviourNet(BehaviourConfig(audio_dim=D, hidden=24, emo_hidden=16, lookahead=lookahead))
    return EmoStreamBehaviour(FakeRuntime(), Avatar(), EmotionTimeline("neutral"), net, hop=hop), net


def audio_ramp(n_frames):
    # frame k has constant value k + 1, so its feature identifies it
    return np.repeat(np.arange(1, n_frames + 1, dtype=np.float32), 640)


def collect(beh, audio, step):
    out, per_push = [], []
    for i in range(0, len(audio), step):
        m = beh.push(audio[i:i + step])
        per_push.append(len(m))
        out += m
    n = -(-len(audio) // 640)
    out += beh.flush(n)
    return out, per_push


@pytest.mark.parametrize("hop", [1, 5])
@pytest.mark.parametrize("lookahead", [0, 2])
def test_every_frame_is_emitted_exactly_once(hop, lookahead):
    beh, _ = make(hop, lookahead)
    out, _ = collect(beh, audio_ramp(23), 800)
    assert len(out) == 23 == beh.frames_out
    assert all(m["exp"].shape == (1, 63) for m in out)


def test_hop1_emits_one_frame_per_frame_of_audio_and_hop5_in_blocks():
    a = audio_ramp(40)
    _, pushes1 = collect(make(1)[0], a, 640)
    _, pushes5 = collect(make(5)[0], a, 640)
    assert set(pushes1[4:]) == {1}                        # steady state: one frame out per frame in
    assert set(pushes5) <= {0, 5} and pushes5.count(5) >= 6  # blocks of five


def test_hop1_and_hop5_feed_the_network_the_same_features():
    """With a feature that depends only on the frame's own audio, both hops must give the
    same motion: the difference between them is purely *when* frames come out."""
    a = audio_ramp(30)
    b1, net = make(1, seed=3)
    b5 = EmoStreamBehaviour(FakeRuntime(), Avatar(), EmotionTimeline("neutral"), net, hop=5)
    o1, _ = collect(b1, a, 1000)
    o5, _ = collect(b5, a, 1000)
    assert np.allclose(np.stack([m["exp"] for m in o1]), np.stack([m["exp"] for m in o5]), atol=1e-5)


def test_lookahead_matches_the_training_time_shift():
    a = audio_ramp(20)
    beh, net = make(1, lookahead=3, seed=1)
    out, _ = collect(beh, a, 640)
    feats = np.stack([np.full(D, k + 1, np.float32) for k in range(20)])
    x = torch.from_numpy(shift_features(feats, 3))[None]
    e = torch.zeros(1, 20, 5)
    e[..., 0] = 1
    with torch.no_grad():
        ref = net(x, e)[0][0].numpy()
    got = np.stack([m["exp"][0] for m in out])
    assert np.allclose(got, ref[:, :63], atol=1e-5)
    assert beh.algorithmic_delay_frames == (6, 6)          # 3 encoder + 3 model look-ahead


def test_base_offset_is_added_to_the_source_expression():
    x = Avatar.x_s_info
    off = np.full(63, 0.01, np.float32)
    m = absolute_motion(x, np.zeros(3, np.float32), np.zeros(69, np.float32), base_offset=off)
    assert np.allclose(m["exp"], 0.01)


# ---- loss ----------------------------------------------------------------------------------
def test_ccc_loss_rewards_amplitude_not_just_correlation():
    t = torch.linspace(0, 12, 100)
    target = torch.sin(t)[None, :, None].repeat(1, 1, 3)
    mask, w = torch.ones(1, 100), torch.ones(3)
    perfect = ccc_loss(target, target, mask, w)
    muted = ccc_loss(0.4 * target, target, mask, w)        # same timing, 40 % amplitude
    shifted = ccc_loss(target + 1.0, target, mask, w)      # same shape, wrong offset
    assert perfect < 1e-3
    assert muted > 0.25 and shifted > 0.25
    assert ccc_loss(0.8 * target, target, mask, w) < muted


def test_ccc_loss_ignores_dimensions_that_do_not_move():
    target = torch.zeros(1, 100, 2)
    target[0, :, 0] = torch.sin(torch.linspace(0, 12, 100))
    pred = target.clone()
    pred[0, :, 1] = torch.randn(100)                       # noise on the still dimension
    assert ccc_loss(pred, target, torch.ones(1, 100), torch.ones(2)) < 1e-3
