"""Wire protocol of the EmoStream live session (one WebSocket per session).

Text messages are JSON objects with a ``type``. Binary messages start with a one-byte
tag. Everything about timing is expressed in samples or frame indices, so the
client can align video with the audio it captured without trusting arrival times.

Client -> server
    text   {"type": "start", "consent": {"portrait": true, "audio": true},
            "sample_rate": 16000, "emotion": "neutral", "intensity": 1.0,
            "model": "emostream", "size": 512, "jpeg_quality": 80,
            "video": "h264", "bitrate_kbps": 900}      -- video: "jpeg" (default) or "h264"
    binary 0x10 | portrait image bytes (PNG/JPEG)               -- once, after "start"
    binary 0x01 | PCM16LE mono audio at the declared sample rate -- repeatedly
    text   {"type": "emotion", "emotion": "happy", "intensity": 0.7, "at_seconds": 3.2?}
    text   {"type": "ack", "frames": n}   -- frames received so far; drives network pacing
    text   {"type": "ping", "t": x}       -- answered at once with {"type": "pong", "t": x}
    text   {"type": "keyframe"}           -- H.264 only: the decoder needs a key frame
    text   {"type": "end"}     -- no more audio: flush the tail, then "done"
    text   {"type": "stop"}    -- discard queued audio and frames, close

Server -> client
    text   {"type": "ready", "session": {...}}                  -- portrait registered
    binary 0x02 | u32 frame_index | u32 latency_ms | JPEG bytes  -- one per video frame (video "jpeg")
    binary 0x03 | u32 frame_index | u32 latency_ms | u8 flags | H.264 Annex-B access unit
                                                                 -- video "h264"; flags bit 0 = key frame
    text   {"type": "pong", "t": x}
    text   {"type": "stats", ...}                                -- about once a second
    text   {"type": "emotion_ack", "at_frame": n}
    text   {"type": "done", "stats": {...}}
    text   {"type": "error", "code": "...", "message": "..."}
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass

TAG_AUDIO = 0x01
TAG_FRAME = 0x02
TAG_VIDEO = 0x03
TAG_PORTRAIT = 0x10
FRAME_HEADER = struct.Struct("<BII")  # tag, frame index, latency in ms
VIDEO_HEADER = struct.Struct("<BIIB")  # tag, frame index, latency in ms, flags (bit 0: key frame)
VIDEO_CODECS = ("jpeg", "h264")

MODELS = ("emostream", "ditto")
SIZES = (256, 384, 512)
SAMPLE_RATES = (16000, 22050, 24000, 32000, 44100, 48000)
MAX_PORTRAIT_BYTES = 12 * 1024 * 1024
MAX_AUDIO_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_SESSION_SECONDS = 15 * 60


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_json(self) -> str:
        return json.dumps({"type": "error", "code": self.code, "message": self.message})


@dataclass(frozen=True)
class StartRequest:
    sample_rate: int
    emotion: str
    intensity: float
    model: str
    size: int
    jpeg_quality: int
    video: str = "jpeg"
    bitrate_kbps: int = 900


def parse_start(msg: dict, emotions) -> StartRequest:
    if msg.get("type") != "start":
        raise ProtocolError("expected_start", "the first message must be a start request")
    consent = msg.get("consent") or {}
    if consent.get("portrait") is not True or consent.get("audio") is not True:
        raise ProtocolError("consent_required",
                            "consent for both the portrait and the audio is required to start a session")
    sr = msg.get("sample_rate", 16000)
    if sr not in SAMPLE_RATES:
        raise ProtocolError("bad_sample_rate", f"sample_rate must be one of {SAMPLE_RATES}")
    emotion, intensity = parse_emotion_fields(msg, emotions)
    model = msg.get("model", "emostream")
    if model not in MODELS:
        raise ProtocolError("bad_model", f"model must be one of {MODELS}")
    size = msg.get("size", 512)
    if size not in SIZES:
        raise ProtocolError("bad_size", f"size must be one of {SIZES}")
    q = msg.get("jpeg_quality", 80)
    if not isinstance(q, int) or not 40 <= q <= 95:
        raise ProtocolError("bad_quality", "jpeg_quality must be an integer from 40 to 95")
    video = msg.get("video", "jpeg")
    if video not in VIDEO_CODECS:
        raise ProtocolError("bad_video", f"video must be one of {VIDEO_CODECS}")
    kbps = msg.get("bitrate_kbps", 900)
    if isinstance(kbps, bool) or not isinstance(kbps, int) or not 200 <= kbps <= 4000:
        raise ProtocolError("bad_bitrate", "bitrate_kbps must be an integer from 200 to 4000")
    return StartRequest(sr, emotion, intensity, model, size, q, video, kbps)


def parse_emotion_fields(msg: dict, emotions) -> tuple[str, float]:
    emotion = msg.get("emotion", "neutral")
    if emotion not in emotions:
        raise ProtocolError("bad_emotion", f"emotion must be one of {tuple(emotions)}")
    intensity = msg.get("intensity", 1.0)
    if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or not 0.0 <= intensity <= 1.0:
        raise ProtocolError("bad_intensity", "intensity must be a number from 0 to 1")
    return emotion, float(intensity)


def parse_text(raw: str) -> dict:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProtocolError("bad_json", "text messages must be JSON") from e
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise ProtocolError("bad_message", "messages need a string 'type'")
    return msg


def split_binary(data: bytes) -> tuple[int, bytes]:
    if not data:
        raise ProtocolError("empty_binary", "empty binary message")
    return data[0], data[1:]


def check_audio_payload(payload: bytes) -> bytes:
    if len(payload) > MAX_AUDIO_MESSAGE_BYTES:
        raise ProtocolError("audio_too_large", "audio message too large")
    if len(payload) % 2:
        raise ProtocolError("bad_audio", "PCM16 audio must have an even number of bytes")
    return payload


def check_portrait_payload(payload: bytes) -> bytes:
    if len(payload) > MAX_PORTRAIT_BYTES:
        raise ProtocolError("portrait_too_large", f"portrait must be at most {MAX_PORTRAIT_BYTES // 2**20} MB")
    if not (payload[:8] == b"\x89PNG\r\n\x1a\n" or payload[:3] == b"\xff\xd8\xff" or payload[:4] == b"RIFF"):
        raise ProtocolError("bad_portrait", "portrait must be a PNG, JPEG or WebP image")
    return payload


def encode_frame(index: int, latency_ms: float, jpeg: bytes) -> bytes:
    return FRAME_HEADER.pack(TAG_FRAME, index, max(0, min(int(round(latency_ms)), 2**32 - 1))) + jpeg


def decode_frame(data: bytes) -> tuple[int, int, bytes]:
    tag, index, latency = FRAME_HEADER.unpack_from(data)
    if tag != TAG_FRAME:
        raise ProtocolError("bad_frame", "not a frame message")
    return index, latency, data[FRAME_HEADER.size:]


def encode_video(index: int, latency_ms: float, key: bool, data: bytes) -> bytes:
    return VIDEO_HEADER.pack(TAG_VIDEO, index, max(0, min(int(round(latency_ms)), 2**32 - 1)), 1 if key else 0) + data


def decode_video(data: bytes) -> tuple[int, int, bool, bytes]:
    tag, index, latency, flags = VIDEO_HEADER.unpack_from(data)
    if tag != TAG_VIDEO:
        raise ProtocolError("bad_frame", "not a video message")
    return index, latency, bool(flags & 1), data[VIDEO_HEADER.size:]
