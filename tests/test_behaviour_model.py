"""CPU tests of the behaviour network, its data pipeline and a miniature training run."""
import numpy as np
import pytest
import torch

from emostream.constants import EXP_DIM, LIP_KEYPOINTS
from emostream.models import MOTION_DIM, BehaviourConfig, BehaviourNet, keypoint_mask
from emostream.training.data import ClipSet, emotion_vector, to_delta
from emostream.training.trainer import TrainConfig, evaluate, train


def _emo(batch, T, emotion="happy", level=3):
    return torch.from_numpy(emotion_vector(emotion, level))[None, None].expand(batch, T, -1).clone()


def _net(seed=0, **kw):
    torch.manual_seed(seed)
    net = BehaviourNet(BehaviourConfig(audio_dim=32, hidden=48, emo_hidden=32, **kw)).eval()
    with torch.no_grad():  # the emotion head is zero-initialised; give it something to do
        net.emo_exp.weight.normal_(0, 0.5)
        net.emo_head.weight.normal_(0, 0.5)
    return net


def test_output_shape_and_parameter_count():
    net = BehaviourNet()
    out, state = net(torch.randn(2, 40, 1024), _emo(2, 40))
    assert out.shape == (2, 40, MOTION_DIM) and MOTION_DIM == 69
    assert 1.0e6 < net.n_parameters() < 2.0e6


@pytest.mark.parametrize("chunk", [1, 4, 5, 7, 25])
def test_chunked_streaming_equals_whole_sequence(chunk):
    net = _net()
    a, e = torch.randn(1, 60, 32), _emo(1, 60)
    with torch.no_grad():
        whole, _ = net(a, e)
        outs, state = [], None
        for i in range(0, 60, chunk):
            o, state = net(a[:, i:i + chunk], e[:, i:i + chunk], state)
            outs.append(o)
    assert torch.allclose(torch.cat(outs, 1), whole, atol=1e-5)


def test_model_is_causal():
    net = _net()
    a, e = torch.randn(1, 50, 32), _emo(1, 50)
    b = a.clone()
    b[:, 30:] = torch.randn(1, 20, 32)
    with torch.no_grad():
        assert torch.allclose(net(a, e)[0][:, :30], net(b, e)[0][:, :30], atol=1e-6)


def test_zero_intensity_equals_neutral_and_articulation_only():
    net = _net()
    a = torch.randn(1, 30, 32)
    with torch.no_grad():
        neutral, _, parts = net(a, _emo(1, 30, "neutral", 1), return_parts=True)
        zero, _ = net(a, _emo(1, 30, "angry", 0))
        full, _ = net(a, _emo(1, 30, "angry", 3))
    assert torch.allclose(neutral, zero, atol=1e-6)
    assert torch.allclose(neutral, parts["art"], atol=1e-6) and parts["emo"].abs().max() == 0
    assert (full - neutral).abs().max() > 1e-3


def test_emotion_changes_do_not_alter_the_articulation_branch():
    net = _net()
    a = torch.randn(1, 30, 32)
    with torch.no_grad():
        p1 = net(a, _emo(1, 30, "happy", 3), return_parts=True)[2]["art"]
        p2 = net(a, _emo(1, 30, "sad", 1), return_parts=True)[2]["art"]
    assert torch.allclose(p1, p2, atol=1e-6)


def test_region_gate_is_capped_on_lips():
    net = _net(lip_cap=0.35)
    with torch.no_grad():
        net.gate_logit.fill_(50.0)  # push every gate to its maximum
        g = net.emotion_gate()
    lip = keypoint_mask(LIP_KEYPOINTS).bool()
    assert g[lip].max() <= 0.35 + 1e-6
    assert g[~lip].min() > 0.99
    assert lip.sum() == 3 * len(LIP_KEYPOINTS)


def test_scale_is_stored_as_ratio():
    rest = np.zeros(MOTION_DIM, np.float32)
    rest[-1] = 1.2
    m = np.tile(rest, (4, 1))
    m[:, -1] = [1.2, 1.32, 1.08, 1.2]
    assert np.allclose(to_delta(m, rest)[:, -1], [0, 0.1, -0.1, 0], atol=1e-6)


# ---- miniature dataset: the mouth follows one audio channel, emotions add fixed offsets ----
def _fake_set(n_actors=3, seed=0):
    rng = np.random.default_rng(seed)
    index, store = [], {}
    lip_dim = LIP_KEYPOINTS[-1] * 3 + 1
    offsets = {"happy": 5, "sad": 8, "angry": 2, "surprised": 30}
    for a in range(n_actors):
        actor = f"A{a}"
        base = rng.normal(0, 0.05, EXP_DIM).astype(np.float32)   # the actor's own face shape
        clips = [("neutral", 1)] * 4 + [(e, lv) for e in offsets for lv in (1, 2, 3)]
        for j, (emo, level) in enumerate(clips):
            T = 80
            audio = rng.normal(0, 1, (T, 32)).astype(np.float32)
            audio[:3] = 0                                         # clips start in silence
            exp = np.tile(base, (T, 1))
            exp[:, lip_dim] += 0.02 * np.tanh(audio[:, 0])        # articulation
            if emo != "neutral":
                exp[:, offsets[emo]] += 0.03 * level / 3          # emotion offset off the lips
            key = f"{actor}_{j}"
            store[key] = {"exp": exp, "pose": np.zeros((T, 3), np.float32), "t": np.zeros((T, 3), np.float32),
                          "scale": np.full(T, 1.2, np.float32), "hubert": audio}
            index.append({"clip_id": key, "actor": actor, "emotion": emo, "level": level, "features": key})
    return ClipSet(index, loader=lambda k: store[k]), lip_dim, offsets


def test_clipset_removes_actor_identity_and_emotion_offset():
    ds, lip_dim, offsets = _fake_set()
    for c in ds.clips:
        assert abs(c["y"][:3].mean()) < 1e-3                       # deltas start at the rest pose
        if c["emotion"] != "neutral":
            d = offsets[c["emotion"]]
            assert c["y"][:, d].mean() == pytest.approx(0.03 * c["level"] / 3, abs=2e-3)
            assert abs(c["y_art"][:, d].mean()) < 2e-3             # articulation target has no emotion offset
    audio, emo, y, y_art, mask = ds.batch(np.random.default_rng(0), 8, 100)
    assert audio.shape == (8, 100, 32) and y.shape == (8, 100, MOTION_DIM)
    assert mask[:, :80].all() and not mask[:, 80:].any()
    assert (emo[:, 80:, 0] == 1).all()


def test_miniature_training_learns_articulation_and_emotion():
    ds, lip_dim, offsets = _fake_set()
    cfg = TrainConfig(steps=400, batch_size=16, length=80, lr=3e-3, eval_every=400,
                      model=BehaviourConfig(audio_dim=32, hidden=48, emo_hidden=32, dropout=0.0))
    res = train(ds, ds, cfg, device="cpu", log=lambda *_: None)
    assert max(res["chunk_max_abs_diff"].values()) < 1e-4
    m = res["best"]
    assert m["lip_corr"] > 0.6, m   # 400 CPU steps on a toy set; real training runs much longer
    assert all(v > 0.8 for v in m["offset_cos"].values()), m["offset_cos"]
