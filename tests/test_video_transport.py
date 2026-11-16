"""H.264 delivery, network pacing and the control messages that support them."""
from __future__ import annotations

import json

import numpy as np
import pytest

from backend.streaming import protocol as P
from backend.streaming.video import ArrivalJitter, H264Encoder, SendPacer, h264_available
from test_backend import START, client, pcm, png_bytes  # noqa: F401  (client is a fixture)

needs_h264 = pytest.mark.skipif(not h264_available(), reason="PyAV with libx264 is not installed")


def test_video_message_round_trip():
    blob = P.encode_video(70000, 123.4, True, b"\x00\x00\x00\x01abc")
    assert P.decode_video(blob) == (70000, 123, True, b"\x00\x00\x00\x01abc")
    assert P.decode_video(P.encode_video(1, 0, False, b"x"))[2] is False


@pytest.mark.parametrize("bad, code", [(dict(START, video="vp9"), "bad_video"),
                                       (dict(START, video="h264", bitrate_kbps=50), "bad_bitrate"),
                                       (dict(START, bitrate_kbps=True), "bad_bitrate")])
def test_start_rejects_bad_video_options(bad, code):
    with pytest.raises(P.ProtocolError) as e:
        P.parse_start(bad, ("neutral", "happy"))
    assert e.value.code == code


def test_start_defaults_to_jpeg():
    req = P.parse_start(START, ("neutral",))
    assert (req.video, req.bitrate_kbps) == ("jpeg", 900)


@needs_h264
def test_encoder_emits_one_decodable_access_unit_per_frame():
    import av

    enc = H264Encoder(256, bitrate_kbps=400)
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (256, 256, 3), dtype=np.uint8)
    units = []
    for k in range(60):
        frame = np.roll(base, k * 2, axis=1)
        data, key = enc.encode(frame)
        assert data.startswith(b"\x00\x00\x00\x01") or data.startswith(b"\x00\x00\x01")   # Annex B
        units.append((data, key))
    assert units[0][1] is True                       # stream starts with a key frame
    assert units[50][1] is True                      # and repeats one every two seconds
    assert sum(k for _, k in units) == 2
    # every access unit decodes to exactly one picture, immediately (no reordering delay)
    dec = av.CodecContext.create("h264", "r")
    for data, _ in units:
        out = dec.decode(av.Packet(data))
        assert len(out) == 1 and (out[0].width, out[0].height) == (256, 256)
    # inter-frame coding: far smaller than independent pictures of this noise would be
    assert sum(len(d) for d, _ in units[1:50]) / 49 < len(units[0][0])


@needs_h264
def test_encoder_key_frame_on_request_and_on_bitrate_change():
    enc = H264Encoder(256, bitrate_kbps=600)
    img = np.full((256, 256, 3), 90, np.uint8)
    assert enc.encode(img)[1] is True
    assert enc.encode(img)[1] is False
    enc.request_key_frame()
    assert enc.encode(img)[1] is True
    enc.set_bitrate(300)
    assert enc.bitrate_kbps == 300 and enc.encode(img)[1] is True
    enc.set_bitrate(10)
    assert enc.bitrate_kbps == 200                    # clamped


def simulate(pacer, seconds, one_way=0.15, stall=None, ack_every=0.2):
    """A link with a fixed one-way delay that delivers nothing during ``stall`` (start, end);
    what was sent meanwhile arrives when it ends. Returns frames sent during the stall."""
    arrivals, acks, sent_in_stall = [], [], 0          # receive times; (arrival time, count)
    next_ack = ack_every
    for k in range(int(seconds * 25)):
        t = k * 0.04
        while acks and acks[0][0] <= t:
            pacer.on_ack(acks.pop(0)[1], t)
        if t >= next_ack:
            next_ack += ack_every
            if not (stall and stall[0] <= t < stall[1]):
                acks.append((t + one_way, sum(1 for a in arrivals if a <= t)))
        if pacer.decide(t):
            at = t + one_way
            if stall and stall[0] <= at < stall[1]:
                at = stall[1]
                sent_in_stall += 1
            arrivals.append(at)
    return sent_in_stall


def test_pacer_sends_everything_on_a_healthy_link():
    for one_way in (0.02, 0.15, 0.4):                 # near, intercontinental, poor
        p = SendPacer()
        simulate(p, 20, one_way=one_way)
        assert (p.skipped, p.congestion_events, p.bitrate_kbps) == (0, 0, 900), one_way


def test_pacer_skips_and_lowers_bitrate_when_the_client_falls_behind_then_recovers():
    p = SendPacer()
    sent_in_stall = simulate(p, 60, stall=(4.0, 7.0))
    assert p.congestion_events >= 1
    assert sent_in_stall < 35                         # 75 frames were due; most were held back
    assert p.skipped > 35
    assert not p.skipping
    assert p.bitrate_kbps == 900                      # restored after clean time


def test_pacer_lowers_bitrate_at_the_first_sign_of_trouble():
    p = SendPacer()
    simulate(p, 8, stall=(4.0, 7.0))
    assert p.bitrate_kbps < 900


def test_pacer_without_acknowledgements_never_skips():
    p = SendPacer()
    assert all(p.decide(k * 0.04) for k in range(300))


def test_arrival_jitter_reports_bursty_uplink():
    j = ArrivalJitter()
    for k in range(50):
        j.add(k * 0.08, (k + 1) * 0.08)               # steady
    assert j.summary()["lag_max_ms"] < 1
    j.add(50 * 0.08 + 0.9, 51 * 0.08)                 # one chunk 900 ms late
    assert 890 < j.summary()["lag_max_ms"] < 910


@needs_h264
def test_session_delivers_h264_and_answers_ping(client):  # noqa: F811
    with client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(dict(START, video="h264", bitrate_kbps=500)))
        ws.send_bytes(bytes([P.TAG_PORTRAIT]) + png_bytes())
        ready = json.loads(ws.receive_text())
        assert ready["session"]["video"] == {"codec": "h264", "bitrate_kbps": 500}
        ws.send_text(json.dumps({"type": "ping", "t": 12.5}))
        ws.send_text(json.dumps({"type": "ack", "frames": 0}))
        ws.send_text(json.dumps({"type": "keyframe"}))
        for n in (3200, 6400):
            ws.send_bytes(pcm(n))
        ws.send_text(json.dumps({"type": "end"}))
        frames, texts = [], []
        while True:
            m = ws.receive()
            if m.get("bytes") is not None:
                frames.append(P.decode_video(m["bytes"]))
            else:
                texts.append(json.loads(m["text"]))
                if texts[-1]["type"] in ("done", "error"):
                    break
    assert [f[0] for f in frames] == list(range(15))
    assert frames[0][2] is True and not all(f[2] for f in frames)
    assert {"type": "pong", "t": 12.5} in texts
    assert texts[-1]["type"] == "done"


def test_info_lists_video_codecs(client):  # noqa: F811
    assert "jpeg" in client.get("/api/info").json()["protocol"]["video"]
