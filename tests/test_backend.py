"""Protocol and API tests with an in-memory engine (no GPU, no model weights)."""
import io
import json
import threading

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.api.app import create_app
from backend.streaming import protocol as P
from emostream.audio import SampleClock, frame_time
from emostream.constants import EMOTIONS, SAMPLES_PER_FRAME
from emostream.engine.emotion import EmotionTimeline
from emostream.engine.session import Frame
from emostream.safety import Watermark


def png_bytes(size=64):
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (120, 90, 60)).save(buf, "PNG")
    return buf.getvalue()


class FakeSession:
    """Emits one grey frame per complete 640-sample frame; brightness encodes the emotion."""

    def __init__(self, req, on_close):
        self.req, self.on_close = req, on_close
        self.clock = SampleClock()
        self.timeline = EmotionTimeline(req.emotion, req.intensity)
        self.out = 0
        self.wm = Watermark()
        self.closed = False

    def _frames(self, upto):
        frames = []
        while self.out < upto:
            emo, inten = self.timeline.at(self.out)
            level = 40 + 40 * EMOTIONS.index(emo)
            rgb = self.wm.apply(np.full((self.req.size, self.req.size, 3), level, np.uint8))
            frames.append(Frame(self.out, frame_time(self.out), rgb, 12.0))
            self.out += 1
        return frames

    def push_pcm(self, pcm16, captured_at=None):
        self.clock.push(len(pcm16) // 2)
        return self._frames(self.clock.complete_frames)

    def set_emotion(self, emotion, intensity, at_seconds=None):
        at = self.clock.total_frames if at_seconds is None else int(round(at_seconds * 25))
        self.timeline.set(emotion, intensity, max(at, self.out))
        return max(at, self.out)

    def end(self):
        self.clock.close()
        return self._frames(self.clock.total_frames)

    def stats(self):
        return {"frames": self.out, "frames_dropped": 0, "audio_s": self.clock.seconds, "compute_fps": 99.0,
                "latency": {"n": self.out, "p50_ms": 12.0, "p95_ms": 12.0}, "stages": {}, "gpu": {}}

    def close(self):
        if not self.closed:
            self.closed = True
            self.on_close()


class FakeProvider:
    def __init__(self):
        self.lock = threading.Lock()
        self.opened = 0
        self.portraits_seen = []

    def info(self):
        return {"gpu": "fake", "models": ["emostream", "ditto"], "emotions": list(EMOTIONS), "busy": self.lock.locked()}

    def open_session(self, portrait, req):
        if not self.lock.acquire(blocking=False):
            raise P.ProtocolError("busy", "another session is running")
        self.opened += 1
        self.portraits_seen.append(len(portrait))
        self.last_session = FakeSession(req, self.lock.release)
        return self.last_session

    def render_file(self, portrait, audio, req):
        s = self.open_session(portrait, req)
        s.close()
        return b"\x00\x00\x00\x18ftypmp42", {"frames": 25, "audio_s": 1.0, "compute_fps": 50.0}


@pytest.fixture()
def client():
    provider = FakeProvider()
    c = TestClient(create_app(provider))
    c.provider = provider
    return c


START = {"type": "start", "consent": {"portrait": True, "audio": True}, "sample_rate": 16000, "size": 256}


def first_message(ws) -> dict:
    """Next text message that is not a startup progress report."""
    while True:
        m = json.loads(ws.receive_text())
        if m.get("type") != "status":
            return m


def pcm(n_samples):
    return bytes([P.TAG_AUDIO]) + (np.zeros(n_samples, "<i2")).tobytes()


def collect(ws, until="done"):
    frames, texts = [], []
    while True:
        m = ws.receive()
        if m.get("bytes") is not None:
            frames.append(P.decode_frame(m["bytes"]))
        else:
            t = json.loads(m["text"])
            texts.append(t)
            if t["type"] in (until, "error"):
                return frames, texts


# ---- protocol unit tests -------------------------------------------------------------------
def test_parse_start_validates_everything():
    ok = P.parse_start(dict(START, emotion="happy", intensity=0.5, model="ditto"), EMOTIONS)
    assert (ok.emotion, ok.intensity, ok.model, ok.size, ok.sample_rate) == ("happy", 0.5, "ditto", 256, 16000)
    bad = [
        ({"type": "hello"}, "expected_start"),
        (dict(START, consent={"portrait": True, "audio": False}), "consent_required"),
        (dict(START, consent={"portrait": "yes", "audio": True}), "consent_required"),
        ({"type": "start"}, "consent_required"),
        (dict(START, sample_rate=8000), "bad_sample_rate"),
        (dict(START, emotion="bored"), "bad_emotion"),
        (dict(START, intensity=1.2), "bad_intensity"),
        (dict(START, intensity=True), "bad_intensity"),
        (dict(START, model="gpt"), "bad_model"),
        (dict(START, size=1024), "bad_size"),
        (dict(START, jpeg_quality=5), "bad_quality"),
    ]
    for msg, code in bad:
        with pytest.raises(P.ProtocolError) as e:
            P.parse_start(msg, EMOTIONS)
        assert e.value.code == code


def test_frame_roundtrip_and_payload_checks():
    blob = P.encode_frame(123456, 87.6, b"JPEGDATA")
    assert P.decode_frame(blob) == (123456, 88, b"JPEGDATA")
    with pytest.raises(P.ProtocolError):
        P.check_audio_payload(b"\x00\x00\x00")
    with pytest.raises(P.ProtocolError):
        P.check_portrait_payload(b"not an image")
    with pytest.raises(P.ProtocolError):
        P.check_portrait_payload(b"\x89PNG\r\n\x1a\n" + b"0" * (P.MAX_PORTRAIT_BYTES + 1))
    assert P.check_portrait_payload(png_bytes())


# ---- HTTP ------------------------------------------------------------------------------------
def test_health_and_info(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    info = client.get("/api/info").json()
    assert info["emotions"] == list(EMOTIONS) and info["protocol"]["frame_period_ms"] == 40


def test_export_requires_consent_and_returns_mp4(client):
    files = {"portrait": ("p.png", png_bytes(), "image/png"), "audio": ("a.wav", b"RIFF0000", "audio/wav")}
    r = client.post("/api/export", files=files, data={"emotion": "happy"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "consent_required"
    r = client.post("/api/export", files=files,
                    data={"emotion": "happy", "portrait_consent": "true", "audio_consent": "true"})
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    assert json.loads(r.headers["x-emostream-stats"])["frames"] == 25
    r = client.post("/api/export", files=files,
                    data={"emotion": "bored", "portrait_consent": "true", "audio_consent": "true"})
    assert r.status_code == 422


# ---- WebSocket -------------------------------------------------------------------------------
def test_full_session_frame_count_and_order(client):
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        assert first_message(ws)["type"] == "ready"
        for n in (3200, 1000, 5000, 700):       # 9900 samples = 15 full frames + a partial one
            ws.send_bytes(pcm(n))
        ws.send_text(json.dumps({"type": "end"}))
        frames, texts = collect(ws)
    assert [f[0] for f in frames] == list(range(16))
    assert texts[-1]["type"] == "done" and texts[-1]["stats"]["frames"] == 16
    assert all(f[2][:3] == b"\xff\xd8\xff" for f in frames)          # every frame is a JPEG
    assert not client.provider.lock.locked()                          # worker slot released


def test_emotion_change_applies_from_the_acknowledged_frame(client):
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        first_message(ws)
        ws.send_bytes(pcm(10 * SAMPLES_PER_FRAME))
        ws.send_text(json.dumps({"type": "emotion", "emotion": "angry", "intensity": 0.8}))
        ws.send_bytes(pcm(10 * SAMPLES_PER_FRAME))
        ws.send_text(json.dumps({"type": "end"}))
        frames, texts = collect(ws)
    ack = next(t for t in texts if t["type"] == "emotion_ack")
    assert ack["at_frame"] == 10 and ack["emotion"] == "angry"
    mean = {i: np.asarray(Image.open(io.BytesIO(j)))[:100, :100].mean() for i, _, j in frames}
    assert abs(mean[9] - 40) < 6 and abs(mean[10] - (40 + 40 * EMOTIONS.index("angry"))) < 6


def test_frames_carry_the_watermark(client):
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        first_message(ws)
        ws.send_bytes(pcm(SAMPLES_PER_FRAME))
        ws.send_text(json.dumps({"type": "end"}))
        frames, _ = collect(ws)
    img = np.asarray(Image.open(io.BytesIO(frames[0][2]))).astype(int)
    corner = img[-40:, :140]
    assert corner.max() > 200 and img[:100, :100].max() < 80          # bright label on a dark frame


@pytest.mark.parametrize("start,code", [
    (dict(START, consent={"portrait": False, "audio": True}), "consent_required"),
    (dict(START, emotion="bored"), "bad_emotion"),
])
def test_bad_start_is_rejected_before_any_engine_work(client, start, code):
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(start))
        assert json.loads(ws.receive_text())["code"] == code
    assert client.provider.opened == 0


def test_portrait_must_be_an_image_and_audio_must_follow(client):
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + b"hello")
        assert json.loads(ws.receive_text())["code"] == "bad_portrait"
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(pcm(640))
        assert json.loads(ws.receive_text())["code"] == "expected_portrait"
    assert client.provider.opened == 0


def test_second_session_is_refused_while_one_is_running_and_slot_frees_on_stop(client):
    with client.websocket_connect("/ws/session") as a:
        a.send_text(json.dumps(START))
        a.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        assert first_message(a)["type"] == "ready"
        with client.websocket_connect("/ws/session") as b:
            b.send_text(json.dumps(START))
            b.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
            assert first_message(b)["code"] == "busy"
        a.send_text(json.dumps({"type": "stop"}))
    assert not client.provider.lock.locked()
    with client.websocket_connect("/ws/session") as c:
        c.send_text(json.dumps(START))
        c.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        assert first_message(c)["type"] == "ready"


def test_progress_is_reported_before_ready(client):
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        assert json.loads(ws.receive_text()) == {"type": "status", "stage": "initializing_portrait"}
        assert json.loads(ws.receive_text())["type"] == "ready"


def test_statistics_before_the_first_frame_do_not_crash():
    """Regression: the live server crashed with KeyError 'ms_per_frame' when statistics were
    requested before any frame existed (user session, 16 Nov 2026 21:47)."""
    from emostream.telemetry import StageTimer

    t = StageTimer()
    with t.time("behaviour"):
        pass
    assert t.summary(0)["behaviour"]["ms_per_frame"] is None
    assert t.summary(5)["behaviour"]["ms_per_frame"] >= 0


def test_engine_fault_is_reported_to_the_client(client):
    def boom(*a, **k):
        raise RuntimeError("simulated engine fault")

    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        assert first_message(ws)["type"] == "ready"
        client.provider.last_session.push_pcm = boom
        ws.send_bytes(pcm(3200))
        err = first_message(ws)
    assert err["type"] == "error" and err["code"] == "internal_error"
    assert not client.provider.lock.locked()          # the slot is released after a fault


def test_audio_queue_is_bounded(client, monkeypatch):
    import backend.api.app as A

    monkeypatch.setattr(A, "MAX_QUEUED_AUDIO_MESSAGES", 3)
    import time as _t

    slow = []

    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(START))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        assert first_message(ws)["type"] == "ready"
        orig = client.provider.last_session.push_pcm

        def stalled(*a, **k):
            _t.sleep(0.5)
            slow.append(1)
            return orig(*a, **k)

        client.provider.last_session.push_pcm = stalled
        for _ in range(20):
            ws.send_bytes(pcm(1280))
        msg = first_message(ws)
        while msg["type"] != "error":
            msg = first_message(ws)
    assert msg["code"] == "overloaded"
