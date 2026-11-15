"""FastAPI application: live WebSocket sessions, offline export, and the static frontend.

``create_app(provider)`` takes any ``EngineProvider`` so the HTTP/WebSocket behaviour
can be tested without a GPU.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from emostream.constants import EMOTIONS, FPS

from ..services.live import encode_jpeg
from ..streaming import protocol as P

STATS_INTERVAL_S = 1.0
MAX_EXPORT_AUDIO_BYTES = 30 * 1024 * 1024


def create_app(provider, static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="EmoStream", version="0.2.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/info")
    def info():
        return {**provider.info(), "protocol": {"audio": "pcm_s16le mono", "frame": "jpeg",
                                                "frame_period_ms": 1000 // FPS}}

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
            req = P.parse_start(P.parse_text(await ws.receive_text()), EMOTIONS)
            first = await ws.receive()
            if first.get("bytes") is None:
                raise P.ProtocolError("expected_portrait", "send the portrait image after the start message")
            tag, payload = P.split_binary(first["bytes"])
            if tag != P.TAG_PORTRAIT:
                raise P.ProtocolError("expected_portrait", "send the portrait image after the start message")
            session = await asyncio.to_thread(provider.open_session, P.check_portrait_payload(payload), req)
            await ws.send_text(json.dumps({"type": "ready", "session": {
                "model": req.model, "size": req.size, "fps": FPS, "emotion": req.emotion,
                "intensity": req.intensity}}))

            queue: asyncio.Queue = asyncio.Queue()
            sent = {"frames": 0, "dropped": 0, "last_stats": time.perf_counter()}

            async def emit(frames):
                for fr in frames:
                    if fr.rgb is None:
                        sent["dropped"] += 1
                        continue
                    jpeg = await asyncio.to_thread(encode_jpeg, fr.rgb, req.jpeg_quality)
                    await ws.send_bytes(P.encode_frame(fr.index, fr.latency_ms, jpeg))
                    sent["frames"] += 1
                now = time.perf_counter()
                if now - sent["last_stats"] >= STATS_INTERVAL_S:
                    sent["last_stats"] = now
                    st = session.stats()
                    await ws.send_text(json.dumps({
                        "type": "stats", "frames": st["frames"], "frames_dropped": st.get("frames_dropped", 0),
                        "audio_s": st["audio_s"], "latency": st["latency"], "compute_fps": st["compute_fps"],
                        "stages_ms": {k: v["ms_per_frame"] for k, v in st["stages"].items()},
                        "gpu": st.get("gpu"), "queued_chunks": queue.qsize()}))

            async def run():
                while True:
                    item = await queue.get()
                    if item is None:
                        await emit(await asyncio.to_thread(session.end))
                        await ws.send_text(json.dumps({"type": "done", "stats": session.stats()}))
                        return
                    pcm, captured = item
                    await emit(await asyncio.to_thread(session.push_pcm, pcm, captured))

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
                    await queue.put((P.check_audio_payload(payload), time.perf_counter()))
                elif msg.get("text") is not None:
                    m = P.parse_text(msg["text"])
                    if m["type"] == "emotion":
                        emotion, intensity = P.parse_emotion_fields(m, EMOTIONS)
                        at = m.get("at_seconds")
                        at_frame = session.set_emotion(emotion, intensity, at if isinstance(at, (int, float)) else None)
                        await ws.send_text(json.dumps({"type": "emotion_ack", "at_frame": at_frame,
                                                       "emotion": emotion, "intensity": intensity}))
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
        finally:
            if worker is not None and not worker.done():
                worker.cancel()
            if session is not None:
                session.close()
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    if static_dir and Path(static_dir).is_dir():
        index = Path(static_dir) / "index.html"

        @app.get("/")
        def root():
            return FileResponse(index)

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:
        @app.get("/")
        def root_missing():
            return JSONResponse({"service": "EmoStream API", "docs": "/api/docs",
                                 "note": "frontend build not bundled"})
    return app
