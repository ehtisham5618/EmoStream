"""CPU-only tests of the engine parts that need no model weights."""
import numpy as np
import pytest

from emostream.audio import SampleClock, SlidingWindowChunker, frame_of_sample, frame_time, pcm16_to_float, resample_to_16k
from emostream.constants import EMOTIONS, FPS, SAMPLE_RATE, SAMPLES_PER_FRAME
from emostream.engine.emotion import EmotionTimeline, ditto_emotion_vector, one_hot_with_intensity
from emostream.safety import ConsentError, Watermark, require_consent
from emostream.telemetry import LatencyTracker, StageTimer, percentile


# ---- timing ----------------------------------------------------------------------------
def test_frame_is_640_samples():
    assert SAMPLES_PER_FRAME == 640 and FPS == 25 and SAMPLE_RATE == 16000
    assert frame_time(25) == pytest.approx(1.0)
    assert frame_of_sample(639) == 0 and frame_of_sample(640) == 1


def test_clock_counts_frames_independent_of_chunking():
    for sizes in ([16000], [1] * 1000 + [15000], [3200] * 5, [777] * 20 + [460]):
        c = SampleClock()
        for i, n in enumerate(sizes):
            c.push(n, now=float(i))
        assert c.n_samples == 16000
        assert c.complete_frames == 25 == c.total_frames
        assert len(c.frame_ready_time) == 25


def test_clock_ready_time_is_arrival_of_last_sample():
    c = SampleClock()
    c.push(639, now=1.0)
    assert c.complete_frames == 0 and c.frame_ready_time == []
    c.push(1, now=2.0)
    assert c.frame_ready_time == [2.0]
    c.push(700, now=3.0)  # 1340 samples: frame 1 complete, frame 2 partial
    assert c.frame_ready_time == [2.0, 3.0]
    assert c.total_frames == 3
    c.close(now=4.0)
    assert c.frame_ready_time == [2.0, 3.0, 4.0]


def test_pcm16_roundtrip_and_resample_length():
    x = (np.sin(np.linspace(0, 20, 4800)) * 20000).astype("<i2")
    f = pcm16_to_float(x.tobytes())
    assert f.dtype == np.float32 and np.abs(f).max() <= 1.0
    assert len(resample_to_16k(f, 48000)) == 1600
    assert len(resample_to_16k(f, 24000)) == 3200
    assert resample_to_16k(f, 16000) is not None and len(resample_to_16k(np.stack([f, f], 1), 16000)) == 4800


# ---- streaming windows -------------------------------------------------------------------
def test_chunker_matches_offline_windows_for_any_chunking():
    rng = np.random.default_rng(0)
    audio = rng.standard_normal(16000 * 3).astype(np.float32)
    ref = SlidingWindowChunker().push(audio)
    for step in (160, 1000, 3200, 5000):
        ch = SlidingWindowChunker()
        got = []
        for i in range(0, len(audio), step):
            got += ch.push(audio[i:i + step])
        assert len(got) == len(ref)
        assert all(np.array_equal(a, b) for a, b in zip(got, ref))


def test_chunker_window_geometry_and_alignment():
    ch = SlidingWindowChunker(3, 5, 2, 80)
    assert ch.window == 6480 and ch.hop == 3200
    assert ch.lookahead_samples == 2 * 640 + 80
    audio = np.arange(1, 6481, dtype=np.float32)
    # first window appears once 5 frames + look-ahead have arrived
    assert ch.push(audio[: 5 * 640 + ch.lookahead_samples - 1]) == []
    w = ch.push(audio[5 * 640 + ch.lookahead_samples - 1: 5 * 640 + ch.lookahead_samples])
    assert len(w) == 1
    assert np.all(w[0][: 3 * 640] == 0)      # left context is silence
    assert w[0][3 * 640] == 1.0              # frame 0 starts right after it


def test_chunker_flush_covers_all_frames():
    ch = SlidingWindowChunker()
    ch.push(np.ones(16000 + 123, dtype=np.float32))  # 26 frames incl. partial
    ch.flush(26)
    assert ch.frames_emitted >= 26 and ch.frames_emitted % 5 == 0


# ---- emotion -----------------------------------------------------------------------------
def test_timeline_piecewise_constant():
    t = EmotionTimeline("neutral", 1.0)
    t.set("happy", 0.5, at_frame=50)
    t.set("angry", 1.0, at_frame=100)
    assert t.at(0) == ("neutral", 1.0) and t.at(49) == ("neutral", 1.0)
    assert t.at(50) == ("happy", 0.5) and t.at(99) == ("happy", 0.5)
    assert t.at(100) == ("angry", 1.0) and t.at(10_000) == ("angry", 1.0)
    assert t.at(-5) == ("neutral", 1.0)


def test_timeline_new_target_replaces_later_ones():
    t = EmotionTimeline()
    t.set("happy", 1.0, 50)
    t.set("sad", 1.0, 100)
    t.set("angry", 0.3, 60)
    assert t.changes() == [(0, "neutral", 1.0), (50, "happy", 1.0), (60, "angry", 0.3)]


def test_timeline_rejects_bad_input():
    with pytest.raises(ValueError):
        EmotionTimeline("bored")
    with pytest.raises(ValueError):
        EmotionTimeline().set("happy", 1.5)


@pytest.mark.parametrize("emotion", EMOTIONS)
def test_emotion_vectors_are_distributions_and_zero_intensity_is_neutral(emotion):
    for fn, n in ((one_hot_with_intensity, 5), (ditto_emotion_vector, 8)):
        v = fn(emotion, 1.0)
        assert v.shape == (n,) and v.sum() == pytest.approx(1.0, abs=1e-5) and (v >= 0).all()
        assert np.allclose(fn(emotion, 0.0), fn("neutral", 1.0), atol=1e-6)
    half = ditto_emotion_vector(emotion, 0.5)
    assert np.allclose(half, (ditto_emotion_vector(emotion, 1.0) + ditto_emotion_vector("neutral", 1.0)) / 2, atol=1e-6)


def test_ditto_vector_peaks_at_the_right_class():
    order = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise", "contempt")
    for emo, name in (("happy", "happy"), ("sad", "sad"), ("angry", "angry"), ("surprised", "surprise")):
        assert order[int(np.argmax(ditto_emotion_vector(emo, 1.0)))] == name


# ---- safety ------------------------------------------------------------------------------
@pytest.mark.parametrize("size", [(256, 256), (512, 512), (720, 1280)])
def test_watermark_changes_only_a_corner(size):
    h, w = size
    frame = np.full((h, w, 3), 128, dtype=np.uint8)
    out = Watermark().apply(frame.copy())
    changed = np.any(out != 128, axis=2)
    assert changed.any(), "watermark must be visible"
    ys, xs = np.where(changed)
    assert ys.min() > h // 2 and xs.max() < w * 0.7     # bottom-left region only
    assert changed.mean() < 0.08
    assert out[changed].max() > 200                     # bright text on a dark plate


def test_consent_is_mandatory():
    require_consent(True, True)
    for a, b in ((False, True), (True, False), (False, False)):
        with pytest.raises(ConsentError):
            require_consent(a, b)


# ---- telemetry ---------------------------------------------------------------------------
def test_percentile():
    xs = list(range(1, 101))
    assert percentile(xs, 50) == pytest.approx(50.5)
    assert percentile(xs, 95) == pytest.approx(95.05)
    assert percentile([7], 95) == 7
    assert np.isnan(percentile([], 50))


def test_latency_tracker_and_stage_timer():
    lt = LatencyTracker()
    for k in range(50):
        lt.record(ready_time=k * 0.04, emit_time=k * 0.04 + 0.1 + (0.2 if k == 49 else 0))
    s = lt.summary()
    assert s["n"] == 50 and s["p50_ms"] == pytest.approx(100, abs=0.5) and s["max_ms"] == pytest.approx(300, abs=0.5)
    assert s["output_fps"] == pytest.approx(49 / (49 * 0.04 + 0.2), abs=0.01)
    st = StageTimer()
    with st.time("a"):
        pass
    assert st.summary(10)["a"]["calls"] == 1


def test_transition_gate_cross_fades_and_reaches_the_target():
    t = EmotionTimeline("neutral")
    t.set("happy", 1.0, at_frame=20)
    hard = [t.blended(f, one_hot_with_intensity, 0) for f in range(18, 34)]
    soft = [t.blended(f, one_hot_with_intensity, 10) for f in range(18, 34)]
    happy, neutral = one_hot_with_intensity("happy", 1.0), one_hot_with_intensity("neutral", 1.0)
    assert np.allclose(hard[1], neutral) and np.allclose(hard[2], happy)          # hard switch at frame 20
    assert np.allclose(soft[1], neutral) and np.allclose(soft[12], happy)          # done 10 frames later
    w = [v[1] for v in soft[2:12]]                                                  # weight of "happy"
    assert all(b > a for a, b in zip(w, w[1:])) and 0 < w[0] < 0.2 and w[-1] < 1.0
    assert all(abs(v.sum() - 1.0) < 1e-6 for v in soft)


def test_transition_gate_handles_a_change_during_a_fade():
    t = EmotionTimeline("neutral")
    t.set("happy", 1.0, at_frame=20)
    t.set("sad", 1.0, at_frame=24)                       # interrupts the first fade
    seq = np.stack([t.blended(f, one_hot_with_intensity, 10) for f in range(18, 40)])
    assert np.abs(np.diff(seq, axis=0)).max() < 0.2      # no jump anywhere
    assert np.allclose(seq[-1], one_hot_with_intensity("sad", 1.0))
