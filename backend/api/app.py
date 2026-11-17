"""FastAPI application: live WebSocket sessions, offline export, and the static frontend.

``create_app(provider)`` takes any ``EngineProvider`` so the HTTP/WebSocket behaviour
can be tested without a GPU.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from emostream.constants import EMOTIONS, FPS

from ..services.live import encode_jpeg
from ..streaming import protocol as P
from ..streaming.video import ArrivalJitter, H264Encoder, SendPacer, h264_available

STATS_INTERVAL_S = 1.0
# Audio waiting to be processed is bounded: 1,500 messages is two minutes of 80 ms chunks.
# A client that is that far ahead of the worker is told so instead of growing the queue.
MAX_QUEUED_AUDIO_MESSAGES = 1500
log = logging.getLogger("emostream.api")


def frontend_build(static_dir: str | None) -> str | None:
    """Identifier written by the frontend build (dist/build.json); None if not bundled."""
    try:
        return json.loads((Path(static_dir) / "build.json").read_text())["build"]
    except Exception:  # noqa: BLE001
        return None
MAX_EXPORT_AUDIO_BYTES = 30 * 1024 * 1024


def create_app(provider, static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="EmoStream", version="0.3.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    build = frontend_build(static_dir)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/info")
    def info():
        return {**provider.info(), "protocol": {"audio": "pcm_s16le mono", "frame": "jpeg",
                                                "video": ["jpeg"] + (["h264"] if h264_available() else []),
                                                "frame_period_ms": 1000 // FPS},
                "frontend_build": build}

    @app.post("/api/export")
    async def export(portrait: UploadFile = File(...), audio: UploadFile = File(...),
                     emotion: str = Form("neutral"), intensity: float = Form(1.0), model: str = Form("emostream"),
                     size: int = Form(512), portrait_consent: bool = Form(False), audio_consent: bool = Form(False)):
        """Renders an uploaded recording to a watermarked MP4. Inputs are not stored."""
        try:
            req = P.parse_start({"type": "start", "consent": {"portrait": portrait_consent, "audio": audio_consent},
                                 "emotion": emotion, "intensity": intensity, "model": model, "size": size},
                                EMOTIONS)
            img = P.check_portrait_payload(await portrait.read())
        except P.ProtocolError as e:
            raise HTTPException(status_code=403 if e.code == "consent_required" else 422,
                                detail={"code": e.code, "message": e.message}) from e
        wav = await audio.read()
        if len(wav) > MAX_EXPORT_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail={"code": "audio_too_large", "message": "audio file too large"})
        try:
            mp4, stats = await asyncio.to_thread(provider.render_file, img, wav, req)
        except P.ProtocolError as e:
            raise HTTPException(status_code=409 if e.code == "busy" else 422,
                                detail={"code": e.code, "message": e.message}) from e
        return Response(mp4, media_type="video/mp4",
                        headers={"Content-Disposition": 'attachment; filename="emostream.mp4"',
                                 "X-EmoStream-Stats": json.dumps({k: stats.get(k) for k in
                                                                  ("frames", "audio_s", "compute_fps")})})

    @app.websocket("/ws/session")
    async def ws_session(ws: WebSocket):
        await ws.accept()
        session = None
        worker: asyncio.Task | None = None
        try:
            start = P.parse_text(await ws.receive_text())
            P.check_live_client(start)
            req = P.parse_start(start, EMOTIONS)
            first = await ws.receive()
            if first.get("bytes") is None:
                raise P.ProtocolError("expected_portrait", "send the portrait image after the start message")
            tag, payload = P.split_binary(first["bytes"])
            if tag != P.TAG_PORTRAIT:
                raise P.ProtocolError("expected_portrait", "send the portrait image after the start message")
            portrait = P.check_portrait_payload(payload)
            await ws.send_text(json.dumps({"type": "status", "stage": "initializing_portrait"}))
            session = await asyncio.to_thread(provider.open_session, portrait, req)
            # Video: H.264 when asked for and available, otherwise independent JPEG frames.
            codec = "h264" if req.video == "h264" and h264_available() else "jpeg"
            encoder = H264Encoder(req.size, req.bitrate_kbps) if codec == "h264" else None
            pacer = SendPacer(bitrate_kbps=req.bitrate_kbps, max_bitrate_kbps=req.bitrate_kbps)
            uplink = ArrivalJitter()
            send_lock = asyncio.Lock()   # frames, statistics and pongs come from different tasks

            async def send_text(obj: dict) -> None:
                async with send_lock:
                    await ws.send_text(json.dumps(obj))

            async def send_bytes(data: bytes) -> None:
                async with send_lock:
                    await ws.send_bytes(data)

            await send_text({"type": "ready", "session": {
                "model": req.model, "size": req.size, "fps": FPS, "emotion": req.emotion,
                "intensity": req.intensity, "portrait": getattr(session, "portrait_info", {}),
                "algorithmic_delay_ms": getattr(session, "algorithmic_delay_ms", None),
                "video": {"codec": codec, "bitrate_kbps": req.bitrate_kbps if codec == "h264" else None},
                "frontend_build": build, "client_build": req.client_build or None}})

            queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUED_AUDIO_MESSAGES)
            sent = {"frames": 0, "dropped": 0, "last_stats": time.perf_counter(), "audio_s": 0.0,
                    "bytes": [], "final": False}

            def encode(rgb):
                if encoder is None:
                    return encode_jpeg(rgb, req.jpeg_quality), True
                encoder.set_bitrate(pacer.bitrate_kbps)
                return encoder.encode(rgb)

            async def emit(frames):
                for fr in frames:
                    if fr.rgb is None:
                        sent["dropped"] += 1
                        continue
                    now = time.perf_counter()
                    # The tail of a finished session is always delivered; otherwise frames are
                    # skipped (before encoding) while the client is falling behind.
                    if sent["final"]:
                        pacer.record_sent(now)
                    elif not pacer.decide(now):
                        continue
                    data, key = await asyncio.to_thread(encode, fr.rgb)
                    if not data:
                        continue
                    msg = (P.encode_video(fr.index, fr.latency_ms, key, data) if encoder is not None
                           else P.encode_frame(fr.index, fr.latency_ms, data))
                    await send_bytes(msg)
                    sent["frames"] += 1
                    sent["bytes"].append((now, len(msg)))
                now = time.perf_counter()
                if now - sent["last_stats"] >= STATS_INTERVAL_S:
                    sent["last_stats"] = now
                    sent["bytes"] = [(t, n) for t, n in sent["bytes"] if now - t <= 2.0]
                    span = max(now - sent["bytes"][0][0], 0.5) if sent["bytes"] else 1.0
                    st = session.stats()
                    await send_text({
                        "type": "stats", "frames": st["frames"], "frames_dropped": st.get("frames_dropped", 0),
                        "audio_s": st["audio_s"], "latency": st["latency"], "compute_fps": st["compute_fps"],
                        "stages_ms": {k: v.get("ms_per_frame") for k, v in st["stages"].items()},
                        "gpu": st.get("gpu"), "queued_chunks": queue.qsize(),
                        "video": {"codec": codec, "target_kbps": pacer.bitrate_kbps if encoder is not None else None,
                                  "sent_kbps": round(sum(n for _, n in sent["bytes"]) * 8 / span / 1000, 1),
                                  "frames_sent": pacer.sent, "frames_skipped_for_network": pacer.skipped,
                                  "in_flight_frames": pacer.in_flight, "backlog_ms": round(pacer.backlog_ms(now)),
                                  "congestion_events": pacer.congestion_events},
                        "uplink": uplink.summary()})

            # Encoding and sending run in their own task, so the GPU computes the next frames
            # while the previous ones are encoded (on an A100 the two in series exceeded
            # 40 ms per frame: 16 % of frames were skipped in the user's session 6).
            out_q: asyncio.Queue = asyncio.Queue(maxsize=50)

            async def sender():
                while True:
                    frames = await out_q.get()
                    if frames is None:
                        return
                    await emit(frames)

            send_task = asyncio.create_task(sender())

            async def run():
                while True:
                    item = await queue.get()
                    if item is None:
                        sent["final"] = True
                        await out_q.put(await asyncio.to_thread(session.end))
                        await out_q.put(None)
                        await send_task
                        await send_text({"type": "done", "stats": session.stats()})
                        return
                    if item[0] == "emotion":
                        # Applied in order with the audio: the change starts after everything
                        # received before it, even if that audio is still waiting to be rendered.
                        _, emotion, intensity, at = item
                        at_frame = session.set_emotion(emotion, intensity, at)
                        await send_text({"type": "emotion_ack", "at_frame": at_frame,
                                         "emotion": emotion, "intensity": intensity})
                        continue
                    _, pcm, captured = item
                    frames = await asyncio.to_thread(session.push_pcm, pcm, captured)
                    if frames:
                        await out_q.put(frames)
                    if send_task.done():
                        send_task.result()      # re-raise a sending error

            worker = asyncio.create_task(run())
            while True:
                if worker.done():
                    worker.result()   # re-raises engine errors
                    break
                recv = asyncio.create_task(ws.receive())
                done, _ = await asyncio.wait({recv, worker}, return_when=asyncio.FIRST_COMPLETED)
                if recv not in done:
                    recv.cancel()
                    continue
                msg = recv.result()
                if msg["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect()
                if msg.get("bytes") is not None:
                    tag, payload = P.split_binary(msg["bytes"])
                    if tag != P.TAG_AUDIO:
                        raise P.ProtocolError("unexpected_binary", "only audio is accepted after the portrait")
                    pcm = P.check_audio_payload(payload)
                    arrived = time.perf_counter()
                    sent["audio_s"] += len(pcm) / 2 / req.sample_rate
                    uplink.add(arrived, sent["audio_s"])
                    try:
                        queue.put_nowait(("audio", pcm, arrived))
                    except asyncio.QueueFull:
                        raise P.ProtocolError(
                            "overloaded", "audio is arriving faster than it can be animated; start a new session") from None
                elif msg.get("text") is not None:
                    m = P.parse_text(msg["text"])
                    if m["type"] == "ack":
                        n = m.get("frames")
                        if isinstance(n, int) and not isinstance(n, bool) and n >= 0:
                            pacer.on_ack(n, time.perf_counter())
                    elif m["type"] == "ping":
                        await send_text({"type": "pong", "t": m.get("t")})
                    elif m["type"] == "keyframe":
                        if encoder is not None:
                            encoder.request_key_frame()
                    elif m["type"] == "emotion":
                        emotion, intensity = P.parse_emotion_fields(m, EMOTIONS)
                        at = m.get("at_seconds")
                        await queue.put(("emotion", emotion, intensity, at if isinstance(at, (int, float)) else None))
                    elif m["type"] == "end":
                        await queue.put(None)
                    elif m["type"] == "stop":
                        break
                    else:
                        raise P.ProtocolError("unknown_type", f"unknown message type {m['type']!r}")
        except P.ProtocolError as e:
            try:
                await ws.send_text(e.to_json())
            except Exception:  # noqa: BLE001
                pass
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            # An engine or server fault. It is logged in full and reported to the client as
            # what it is, so the page can say so and offer a retry instead of a bare disconnect.
            log.exception("live session failed")
            try:
                await ws.send_text(json.dumps({"type": "error", "code": "internal_error",
                                               "message": f"the server hit an internal error ({type(e).__name__})"}))
            except Exception:  # noqa: BLE001
                pass
        finally:
            if worker is not None and not worker.done():
                worker.cancel()
            st = locals().get("send_task")
            if st is not None and not st.done():
                st.cancel()
            if session is not None:
                session.close()
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    if static_dir and Path(static_dir).is_dir():
        index = Path(static_dir) / "index.html"

        # The page itself must never come from a cache: its script names change with every
        # build, and a cached page keeps running an old client against a new server
        # (that happened in the user's session of 16 Nov 2026, 21:49).
        no_store = {"Cache-Control": "no-store, max-age=0"}

        @app.get("/")
        def root():
            return FileResponse(index, headers=no_store)

        @app.get("/index.html")
        def root_index():
            return FileResponse(index, headers=no_store)

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:
        @app.get("/")
        def root_missing():
            return JSONResponse({"service": "EmoStream API", "docs": "/api/docs",
                                 "note": "frontend build not bundled"})
    return app
