"""The live WavLM stream must produce exactly the offline features (no GPU, a tiny random WavLM)."""
import numpy as np
import pytest

transformers = pytest.importorskip("transformers")


@pytest.fixture(scope="module")
def tiny():
    from transformers import Wav2Vec2FeatureExtractor, WavLMConfig, WavLMModel

    cfg = WavLMConfig(hidden_size=32, num_hidden_layers=3, num_attention_heads=2, intermediate_size=64,
                      conv_dim=(16,) * 7, num_conv_pos_embeddings=16, num_conv_pos_embedding_groups=2)
    import torch

    torch.manual_seed(0)
    return WavLMModel(cfg).eval(), Wav2Vec2FeatureExtractor(do_normalize=True, return_attention_mask=False)


def make(tiny, future=2, past_s=0.4):
    from emostream.audio.wavlm import WavLMFeatures

    model, fe = tiny
    return WavLMFeatures(layer=2, past_s=past_s, future_frames=future, model=model, extractor=fe)


@pytest.mark.parametrize("future", [1, 2, 4])
@pytest.mark.parametrize("chunk", [137, 640, 1280, 3200])
def test_live_stream_equals_offline_features(tiny, future, chunk):
    from emostream.audio.wavlm import WavLMStream

    x = make(tiny, future)
    rng = np.random.default_rng(1)
    n = 40
    audio = (rng.standard_normal(n * 640) * 0.1).astype(np.float32)
    off = x.frames(audio, n, batch=7)
    s = WavLMStream(x)
    got = [s.push(audio[i:i + chunk]) for i in range(0, len(audio), chunk)]
    got.append(s.flush(n))
    live = np.concatenate(got, 0)
    assert live.shape == off.shape
    assert np.abs(live - off).max() < 1e-4


def test_frame_waits_for_its_look_ahead(tiny):
    from emostream.audio.wavlm import WavLMStream

    s = WavLMStream(make(tiny, future=2))
    assert len(s.push(np.zeros(640 * 3 - 1, np.float32))) == 0      # frame 0 needs frames 1 and 2 as well
    assert len(s.push(np.zeros(1, np.float32))) == 1
    assert s.delay_frames == 2


def test_feature_depends_only_on_allowed_audio(tiny):
    """Changing audio after frame k + future must not change frame k's feature."""
    x = make(tiny, future=2)
    rng = np.random.default_rng(2)
    a = (rng.standard_normal(30 * 640) * 0.1).astype(np.float32)
    b = a.copy()
    b[(10 + 1 + 2) * 640:] = rng.standard_normal(len(b) - 13 * 640).astype(np.float32)
    fa, fb = x.frames(a, 30), x.frames(b, 30)
    assert np.abs(fa[:11] - fb[:11]).max() < 1e-5
    assert np.abs(fa[11:] - fb[11:]).max() > 1e-3


def test_batched_many_clips_equal_single_clip_features(tiny):
    x = make(tiny, future=2)
    rng = np.random.default_rng(3)
    lens = [7, 30, 12]
    audios = [(rng.standard_normal(n * 640 - 100) * 0.1).astype(np.float32) for n in lens]
    many = x.frames_many(audios, lens, batch=5)
    for a, n, m in zip(audios, lens, many):
        assert np.abs(x.frames(a, n) - m).max() < 1e-4
