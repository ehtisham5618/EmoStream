"""End-to-end test of a running EmoStream server over its public WebSocket.

Sends a portrait, then a WAV file in 200 ms chunks at microphone pace, changes the
emotion once, and reports what a browser would experience: frames received, frame
rate, and the time from sending the audio that completes a frame to receiving that
frame (network both ways + engine).

    python -m evaluation.benchmarks.ws_client --url https://<app>.modal.run \
        --portrait portrait.png --audio speech.wav --seconds 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import struct
import time
import urllib.request

import numpy as np
import soundfile as sf
import websockets

SR, SPF, CHUNK = 16000, 640, 3200


def load_audio(path: str, seconds: float) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim == 2:
        audio = audio.mean(1)
    if sr != SR:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(sr, SR)
        audio = resample_poly(audio, SR // g, sr // g).astype(np.float32)
    if seconds > 0:
        audio = np.tile(audio, int(np.ceil(seconds * SR / len(audio))))[: int(seconds * SR)]
    return audio


async def run(args) -> dict:
    base = args.url.rstrip("/")
    info = json.loads(urllib.request.urlopen(base + "/api/info", timeout=600).read())  # also triggers a cold start
    audio = load_audio(args.audio, args.seconds)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    portrait = open(args.portrait, "rb").read()
    sent_at: dict[int, float] = {}
    frames: list[tuple[int, float, int]] = []   # index, receive time, server latency
    texts: list[dict] = []
    saved = 0

    async with websockets.connect(base.replace("http", "ws", 1) + "/ws/session", max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "consent": {"portrait": True, "audio": True},
                                  "sample_rate": SR, "emotion": "neutral", "intensity": 1.0,
                                  "model": args.model, "size": args.size}))
        await ws.send(bytes([0x10]) + portrait)
        t_ready = time.perf_counter()
        ready = json.loads(await ws.recv())
        if ready.get("type") != "ready":
            return {"error": ready}
        register_s = time.perf_counter() - t_ready

        async def sender():
            t0 = time.perf_counter()
            n = 0
            switched = False
            for i in range(0, len(pcm), CHUNK):
                chunk = pcm[i:i + CHUNK]
                due = t0 + (i + len(chunk)) / SR
                await asyncio.sleep(max(0.0, due - time.perf_counter()))
                before, n = n // SPF, n + len(chunk)
                await ws.send(bytes([0x01]) + chunk.tobytes())
                now = time.perf_counter()
                for k in range(before, n // SPF):
                    sent_at[k] = now
                if not switched and n >= len(pcm) // 2:
                    switched = True
                    await ws.send(json.dumps({"type": "emotion", "emotion": args.switch_to, "intensity": 1.0}))
            await ws.send(json.dumps({"type": "end"}))

        task = asyncio.create_task(sender())
        while True:
            msg = await ws.recv()
            if isinstance(msg, (bytes, bytearray)):
                _, idx, lat = struct.unpack_from("<BII", msg)
                frames.append((idx, time.perf_counter(), lat))
                if args.save_frames and idx % 100 == 50 and saved < 6:
                    open(f"{args.save_frames}/frame_{idx:05d}.jpg", "wb").write(msg[9:])
                    saved += 1
            else:
                m = json.loads(msg)
                texts.append(m)
                if m["type"] in ("done", "error"):
                    break
        await task

    trips = [1000 * (t - sent_at[i]) for i, t, _ in frames if i in sent_at]
    trips_s = sorted(trips[25:]) if len(trips) > 50 else sorted(trips)
    span = frames[-1][1] - frames[0][1] if len(frames) > 1 else 0
    q = lambda p: round(trips_s[min(len(trips_s) - 1, int(p * len(trips_s)))], 1) if trips_s else None  # noqa: E731
    done = next((m for m in texts if m["type"] == "done"), None)
    return {
        "server": {k: info.get(k) for k in ("gpu", "renderer", "models")},
        "model": args.model, "audio_s": round(len(pcm) / SR, 2), "expected_frames": -(-len(pcm) // SPF),
        "frames_received": len(frames), "in_order": [f[0] for f in frames] == sorted(f[0] for f in frames),
        "received_fps": round((len(frames) - 1) / span, 2) if span else None,
        "portrait_ready_s": round(register_s, 2),
        "client_round_trip_ms": {"p50": q(0.5), "p95": q(0.95), "max": round(max(trips_s), 1) if trips_s else None},
        "server_latency_ms": (done or {}).get("stats", {}).get("latency"),
        "frames_skipped_by_server": (done or {}).get("stats", {}).get("frames_dropped"),
        "emotion_ack": next((m for m in texts if m["type"] == "emotion_ack"), None),
        "errors": [m for m in texts if m["type"] == "error"],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--portrait", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--model", default="emostream")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--switch-to", default="happy")
    ap.add_argument("--save-frames", default="")
    print(json.dumps(asyncio.run(run(ap.parse_args())), indent=1))
