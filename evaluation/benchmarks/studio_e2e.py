"""End-to-end check of the product Studio (web/) in a real browser.

Drives /app/studio in Chromium with a fake microphone (optionally a WAV file), watches the
WebSocket at the message level, and checks the behaviour the integration must guarantee:
consent gating, no audio before "ready", no burst at the start, live H.264 frames drawn on
the stage canvas, emotion and intensity messages (0-1 on the wire), pause/resume, stop with
"end"/"done", avatar-voice playback, export of the take, the diagnostics file, Sessions and
Analytics fed by the real take, and page routes served by the backend.

    # local timing stand-in (no GPU)
    python -m evaluation.benchmarks.fake_server --dist web/dist/client --diagnostics frontend/dist --video clip.mp4 --port 8765
    python -m evaluation.benchmarks.studio_e2e --url http://127.0.0.1:8765 --out result.json

    # deployed worker, the user's portrait and recording as microphone
    python -m evaluation.benchmarks.studio_e2e --url https://<app>.modal.run --portrait p.png --mic-wav speech48k.wav
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
import urllib.request

from evaluation.benchmarks.browser_playback import HOOK, summarise


def run(url: str, portrait: str | None, mic_wav: str | None, speak_s: float, headed: bool, downloads: str) -> dict:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    if portrait is None:
        buf = io.BytesIO()
        Image.new("RGB", (512, 512), (150, 120, 100)).save(buf, "PNG")
        portrait_payload = {"name": "portrait.png", "mimeType": "image/png", "buffer": buf.getvalue()}
    else:
        portrait_payload = portrait
    args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
    if mic_wav:
        args.append(f"--use-file-for-fake-audio-capture={mic_wav}")
    os.makedirs(downloads, exist_ok=True)

    checks: dict[str, dict] = {}

    def check(name: str, ok: bool, detail=None):
        checks[name] = {"ok": bool(ok), "detail": detail}
        print(("PASS " if ok else "FAIL ") + name + ("" if detail is None else f"  {detail}"), flush=True)

    # message log: (t, direction, kind, info)
    log: list[tuple[float, str, str, object]] = []

    def on_ws(ws):
        if not ws.url.endswith("/ws/session"):
            return

        def sent(payload):
            t = time.time()
            if isinstance(payload, (bytes, bytearray)):
                log.append((t, "out", f"bin{payload[0]:#04x}", len(payload)))
            else:
                try:
                    m = json.loads(payload)
                except ValueError:
                    m = {"type": "?"}
                log.append((t, "out", m.get("type", "?"), m))

        def received(payload):
            t = time.time()
            if isinstance(payload, (bytes, bytearray)):
                log.append((t, "in", f"bin{payload[0]:#04x}", len(payload)))
            else:
                try:
                    m = json.loads(payload)
                except ValueError:
                    m = {"type": "?"}
                log.append((t, "in", m.get("type", "?"), m))

        ws.on("framesent", sent)
        ws.on("framereceived", received)

    def first(direction, kind):
        return next((e for e in log if e[1] == direction and e[2] == kind), None)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, args=args)
        ctx = browser.new_context(permissions=["microphone"], accept_downloads=True, viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.add_init_script(HOOK)
        console = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in ("error",) else None)
        page.on("websocket", on_ws)

        # 1. the Studio page loads from the backend
        resp = page.goto(url.rstrip("/") + "/app/studio", wait_until="networkidle", timeout=180000)
        check("01 studio page served (SPA route) and not cached",
              resp is not None and resp.status == 200 and "no-store" in (resp.headers.get("cache-control") or ""),
              resp.headers.get("cache-control") if resp else None)
        start_btn = page.get_by_role("button", name="Start session")

        # 2. nothing can start without a portrait
        check("02 start disabled without portrait", start_btn.is_disabled())

        # 3. upload: real file input, no artificial delay
        t_up = time.time()
        page.set_input_files('input[aria-label="Upload portrait"]', portrait_payload)
        page.get_by_role("checkbox", name="Confirm portrait consent").wait_for(timeout=10000)
        check("03 portrait accepted", True, f"{time.time() - t_up:.2f} s to consent box")

        # 4. consent gating: portrait consent alone is not enough
        page.get_by_role("checkbox", name="Confirm portrait consent").click()
        only_portrait = start_btn.is_disabled()
        page.get_by_role("checkbox", name="Confirm voice consent").click()
        page.wait_for_timeout(200)
        check("04 both consents required", only_portrait and start_btn.is_enabled())

        # 5. start: status stages, then ready; no audio before ready
        clicked = time.time()
        start_btn.click()
        page.wait_for_function(
            "() => window.__draws.length > 10 || document.body.innerText.includes('Something stopped the session')",
            timeout=300000)
        if "Something stopped the session" in page.inner_text("body"):
            check("05 session started", False, page.inner_text("body")[:400])
            browser.close()
            return {"checks": checks, "console": console}
        ready = first("in", "ready")
        audio = [e for e in log if e[1] == "out" and e[2] == "bin0x01"]
        before_ready = [e for e in audio if ready and e[0] < ready[0]]
        status = first("in", "status")
        check("05 status before ready, no audio before ready",
              ready is not None and status is not None and status[0] <= ready[0] and not before_ready,
              {"ready_after_s": round(ready[0] - clicked, 2) if ready else None, "audio_before_ready": len(before_ready)})
        start_msg = first("out", "start")[3]
        check("06 start message: both consents, h264, intensity 0-1",
              start_msg["consent"] == {"portrait": True, "audio": True} and start_msg["video"] == "h264"
              and 0 <= start_msg["intensity"] <= 1, {k: start_msg[k] for k in ("video", "intensity", "emotion", "client_build")})

        # 7. no burst: the first audio messages are microphone-sized chunks at microphone pace
        page.wait_for_timeout(3000)
        audio = [e for e in log if e[1] == "out" and e[2] == "bin0x01"]
        first_s = [e for e in audio if e[0] - audio[0][0] < 1.0] if audio else []
        max_bytes = max((e[3] for e in audio[:20]), default=0)
        check("07 no burst of buffered audio at start", audio and max_bytes <= 1 + 2 * 1280 and len(first_s) <= 16,
              {"messages_in_first_second": len(first_s), "largest_first_20": max_bytes})

        # 8. live frames on the stage canvas, H.264
        frames = [e for e in log if e[1] == "in" and e[2] == "bin0x03"]
        check("08 live H.264 frames drawn on the stage", len(frames) > 25 and page.evaluate("() => window.__draws.length") > 25,
              {"h264_frames": len(frames), "jpeg_frames": len([e for e in log if e[2] == 'bin0x02']),
               "first_frame_after_click_s": round(frames[0][0] - clicked, 2) if frames else None})
        check("09 stage shows Live and the AI-generated watermark",
              page.get_by_text("AI-generated · EmoStream").count() > 0 and page.get_by_text("Live", exact=True).count() > 0)

        # 10. avatar voice playback switch
        sw = page.get_by_role("switch", name="Hear the avatar's voice")
        sw.click()
        page.wait_for_timeout(1500)
        voice = page.evaluate("() => { const v = window.__emostream && window.__emostream.voice(); return v ? {scheduled: v.scheduled, missed: v.missed, state: v.ctx.state} : null; }")
        check("10 avatar voice scheduled on the picture's timeline", sw.get_attribute("aria-checked") == "true" and voice and voice["scheduled"] > 0, voice)

        # 11. emotion change and intensity (0-1 on the wire), acknowledged
        page.get_by_role("radio", name="Happy").click()
        page.wait_for_timeout(800)
        slider = page.get_by_role("slider")
        slider.focus()
        page.keyboard.press("End")              # 100 %
        page.wait_for_timeout(800)
        emo = [e[3] for e in log if e[1] == "out" and e[2] == "emotion"]
        acks = [e[3] for e in log if e[1] == "in" and e[2] == "emotion_ack"]
        check("11 emotion + intensity sent (0-1) and acknowledged",
              any(m["emotion"] == "happy" for m in emo) and any(abs(m["intensity"] - 1.0) < 1e-6 for m in emo) and len(acks) >= 1,
              {"sent": emo[-3:], "acks": len(acks)})

        # 12. pause sends no audio; resume sends again
        page.wait_for_timeout(max(0.0, speak_s - 6) * 1000)
        page.get_by_role("button", name="Pause").click()
        page.wait_for_timeout(500)
        n0 = len([e for e in log if e[1] == "out" and e[2] == "bin0x01"])
        page.wait_for_timeout(2000)
        n1 = len([e for e in log if e[1] == "out" and e[2] == "bin0x01"])
        page.get_by_role("button", name="Resume").click()
        page.wait_for_timeout(2500)
        n2 = len([e for e in log if e[1] == "out" and e[2] == "bin0x01"])
        check("12 pause stops audio, resume restarts it", n1 == n0 and n2 > n1, {"during_pause": n1 - n0, "after_resume": n2 - n1})

        # measurements while live
        tel = page.get_by_role("button", name="Technical telemetry")
        if tel.get_attribute("aria-expanded") != "true":
            tel.click()
        page.wait_for_timeout(600)
        telemetry = page.locator("section[aria-label='Timeline'] dl").all_inner_texts()
        draws = page.evaluate("() => window.__draws")
        logs_js = page.evaluate("""() => { const e = window.__emostream; const v = e.voice();
            return { shown: e.player.shownLog, played: v ? v.playedLog : [] }; }""")

        # 13. stop: end -> done -> complete
        page.get_by_role("button", name="Stop").click()
        page.get_by_text("Session complete").first.wait_for(timeout=30000)
        check("13 stop sends end, engine answers done, take completes",
              first("out", "end") is not None and first("in", "done") is not None)

        # 14. export of the take (browser recording)
        with page.expect_download(timeout=20000) as dl:
            page.get_by_role("button", name="Export").click()
        path = os.path.join(downloads, dl.value.suggested_filename)
        dl.value.save_as(path)
        check("14 export downloads the take", os.path.getsize(path) > 10000, {"file": dl.value.suggested_filename, "bytes": os.path.getsize(path)})

        # 15. diagnostics file
        with page.expect_download(timeout=20000) as dl:
            page.get_by_role("button", name="Save diagnostics file").click()
        dpath = os.path.join(downloads, "studio-diagnostics.json")
        dl.value.save_as(dpath)
        diag = json.load(open(dpath, encoding="utf-8"))
        check("15 diagnostics file saved with rows and startup timing",
              len(diag.get("rows", [])) > 5 and diag["startup"]["firstFrameMs"] is not None,
              {"rows": len(diag.get("rows", [])), "startup": diag["startup"], "gpu": diag.get("gpu")})

        # 16. Sessions and Analytics show the real take (client-side navigation keeps the tab state)
        page.get_by_role("link", name="Sessions").first.click()
        try:  # the page is a separately loaded chunk; over the network it can take a moment
            page.get_by_text("take 1").first.wait_for(timeout=15000)
        except Exception:  # noqa: BLE001 - reported by the check below
            pass
        sessions_ok = page.get_by_text("take 1").count() > 0 and page.get_by_text("Real records · this tab").count() > 0
        page.get_by_role("link", name="Analytics").first.click()
        try:
            page.get_by_text("Your latest take this visit").first.wait_for(timeout=15000)
        except Exception:  # noqa: BLE001 - reported by the check below
            pass
        page.wait_for_timeout(800)
        analytics_ok = page.get_by_text("Your latest take this visit").count() > 0 and page.locator(".recharts-surface").count() >= 3
        check("16 Sessions and Analytics use the real take", sessions_ok and analytics_ok,
              {"sessions": sessions_ok, "analytics": analytics_ok})
        if downloads:
            page.screenshot(path=os.path.join(downloads, "analytics_after_take.png"), full_page=True)

        # per-second counts recorded for the take must be plausible (25 per second expected; a
        # counter restarting at pause/resume would show the cumulative total instead)
        delivered = page.evaluate("() => window.__emostream.series().delivered")
        check("16b per-second frame counts plausible across pause/resume", delivered and max(delivered) <= 60,  # catch-up after resume reaches ~35; the reset bug showed ~350
              {"max_per_second": max(delivered) if delivered else None, "seconds": len(delivered)})

        # 17. no console errors during the session
        check("17 no console errors", not console, console[:5])
        browser.close()

    # engine-side numbers from the WebSocket
    stats = [e[3] for e in log if e[1] == "in" and e[2] == "done"]
    out = {
        "checks": checks,
        "passed": sum(c["ok"] for c in checks.values()),
        "total": len(checks),
        "playback": summarise(draws, speak_s, 0),
        "telemetry_panel": telemetry,
        "server_final": stats[-1].get("stats") if stats else None,
        "console": console,
    }
    if logs_js["played"] and logs_js["shown"]:
        import bisect

        import numpy as np

        played = sorted(logs_js["played"])
        firsts = [q[0] for q in played]
        diffs = []
        for k, t_draw in logs_js["shown"]:
            i = bisect.bisect_right(firsts, k * 640) - 1
            if i < 0 or k * 640 - played[i][0] > 16000 * 0.3:
                continue
            diffs.append(t_draw - (played[i][1] + (k * 640 - played[i][0]) / 16))
        out["sync_log"] = {"shown": logs_js["shown"], "played": logs_js["played"],
                           "pause_wall_s": [e[0] for e in log if e[1] == "out" and e[2] == "bin0x01"][:1]}
        if diffs:
            d = np.asarray(diffs)
            out["picture_minus_sound_ms"] = {"p50": round(float(np.median(d)), 1), "p95": round(float(np.percentile(d, 95)), 1),
                                             "within_80_ms": round(float((np.abs(d) <= 80).mean()), 3), "n": int(len(d))}
    return out


def run_file(url: str, portrait: str | None, audio: str, headed: bool, downloads: str) -> dict:
    """Audio-file take: the clip is streamed at speaking pace, played in step with the picture,
    the take ends by itself, and Export renders an MP4 through the engine (/api/export)."""
    from PIL import Image
    from playwright.sync_api import sync_playwright

    if portrait is None:
        buf = io.BytesIO()
        Image.new("RGB", (512, 512), (150, 120, 100)).save(buf, "PNG")
        portrait = {"name": "portrait.png", "mimeType": "image/png", "buffer": buf.getvalue()}
    os.makedirs(downloads, exist_ok=True)
    checks: dict[str, dict] = {}

    def check(name, ok, detail=None):
        checks[name] = {"ok": bool(ok), "detail": detail}
        print(("PASS " if ok else "FAIL ") + name + ("" if detail is None else f"  {detail}"), flush=True)

    log: list[tuple[float, str, str, object]] = []

    def on_ws(ws):
        if not ws.url.endswith("/ws/session"):
            return

        def entry(direction):
            def f(payload):
                if isinstance(payload, (bytes, bytearray)):
                    log.append((time.time(), direction, f"bin{payload[0]:#04x}", len(payload)))
                else:
                    try:
                        m = json.loads(payload)
                    except ValueError:
                        m = {"type": "?"}
                    log.append((time.time(), direction, m.get("type", "?"), m))
            return f

        ws.on("framesent", entry("out"))
        ws.on("framereceived", entry("in"))

    with sync_playwright() as p:
        # no fake microphone: an audio-file take must not need one
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.add_init_script(HOOK)
        page.add_init_script("""(() => { window.__gum = 0; const o = navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
          if (o) navigator.mediaDevices.getUserMedia = function (...a) { window.__gum++; return o.apply(this, a); }; })();""")
        console = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("websocket", on_ws)
        page.goto(url.rstrip("/") + "/app/studio", wait_until="networkidle", timeout=180000)
        page.set_input_files('input[aria-label="Upload portrait"]', portrait)
        page.get_by_role("checkbox", name="Confirm portrait consent").click()

        page.get_by_role("tab", name="Audio file").click()
        start_btn = page.get_by_role("button", name="Start session")
        no_file = start_btn.is_disabled()
        page.set_input_files('input[aria-label="Upload audio file"]', audio)
        page.get_by_text(os.path.basename(audio)).wait_for(timeout=20000)
        page.get_by_role("checkbox", name="Confirm voice consent").click()
        page.wait_for_timeout(200)
        check("F1 audio-file tab: start needs a file, then is enabled", no_file and start_btn.is_enabled())

        clicked = time.time()
        start_btn.click()
        page.get_by_text("Session complete").first.wait_for(timeout=300000)
        ready = next((e for e in log if e[1] == "in" and e[2] == "ready"), None)
        audio_msgs = [e for e in log if e[1] == "out" and e[2] == "bin0x01"]
        before = [e for e in audio_msgs if ready and e[0] < ready[0]]
        first_s = [e for e in audio_msgs if audio_msgs and e[0] - audio_msgs[0][0] < 1.0]
        check("F2 no audio before ready; sent at speaking pace (200 ms chunks)",
              ready and not before and audio_msgs and len(first_s) <= 7,
              {"messages": len(audio_msgs), "first_second": len(first_s), "chunk_bytes": audio_msgs[0][3] if audio_msgs else None})
        frames = [e for e in log if e[1] == "in" and e[2] == "bin0x03"]
        check("F3 live H.264 frames drawn; take ended by itself with end/done",
              len(frames) > 50 and page.evaluate("() => window.__draws.length") > 50
              and any(e[2] == "end" for e in log if e[1] == "out") and any(e[2] == "done" for e in log if e[1] == "in"),
              {"frames": len(frames), "seconds": round(time.time() - clicked, 1)})
        check("F4 microphone never requested", page.evaluate("() => window.__gum") == 0)
        off = page.evaluate("() => window.__emostream.player.stats().avOffsetMs")
        check("F5 picture locked to the playback clock", off is not None and abs(off) < 80, {"av_offset_ms": off})

        with page.expect_download(timeout=300000) as dl:
            page.get_by_role("button", name="Export MP4").click()
        mp4 = os.path.join(downloads, dl.value.suggested_filename)
        dl.value.save_as(mp4)
        head = open(mp4, "rb").read(12)
        check("F6 Export MP4 rendered by the engine and downloaded",
              mp4.endswith(".mp4") and os.path.getsize(mp4) > 10000 and head[4:8] == b"ftyp",
              {"file": os.path.basename(mp4), "bytes": os.path.getsize(mp4)})
        with page.expect_download(timeout=20000) as dl:
            page.get_by_role("button", name="Download the browser recording (WebM) instead").click()
        webm = os.path.join(downloads, dl.value.suggested_filename)
        dl.value.save_as(webm)
        check("F7 browser recording (WebM) also available", os.path.getsize(webm) > 10000, {"bytes": os.path.getsize(webm)})

        page.get_by_role("link", name="Sessions").first.click()
        try:
            page.get_by_text("take 1").first.wait_for(timeout=15000)
        except Exception:  # noqa: BLE001 - reported by the check below
            pass
        check("F8 Sessions lists the take as an audio-file take", page.get_by_text("Audio file").count() > 0)
        check("F9 no console errors", not console, console[:5])
        browser.close()
    return {"file_checks": checks, "file_passed": sum(c["ok"] for c in checks.values()), "file_total": len(checks)}


def route_checks(url: str) -> dict:
    """Pages and files as served by the backend, without a browser."""
    res = {}
    for path in ("/", "/app/studio", "/app/sessions", "/research", "/diagnostics/", "/build.json", "/api/info"):
        req = urllib.request.Request(url.rstrip("/") + path, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read().decode("utf-8", "replace")
            res[path] = {"status": r.status, "cache_control": r.headers.get("cache-control"), "type": r.headers.get("content-type")}
        if path in ("/", "/diagnostics/"):
            # every script the page loads must exist (a wrong build base breaks the page silently)
            import re

            scripts = re.findall(r'<script[^>]+src="([^"]+)"', body)
            res[path]["scripts"] = {}
            for s in scripts:
                with urllib.request.urlopen(url.rstrip("/") + s, timeout=120) as r2:
                    res[path]["scripts"][s] = r2.status
            assert scripts and all(s.startswith(path) for s in scripts), (path, scripts)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--portrait", default=None)
    ap.add_argument("--mic-wav", default=None, help="48 kHz WAV played as the microphone")
    ap.add_argument("--seconds", type=float, default=20, help="speaking time before pause/stop checks")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--downloads", default="outputs/studio_e2e")
    ap.add_argument("--audio-file", default="", help="also run an audio-file take with this clip (MP4 export)")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    res = {"routes": route_checks(a.url)}
    res.update(run(a.url, a.portrait, a.mic_wav, a.seconds, a.headed, a.downloads))
    if a.audio_file:
        res.update(run_file(a.url, a.portrait, a.audio_file, a.headed, a.downloads))
    print(json.dumps({k: v for k, v in res.items() if k != "checks"}, indent=1)[:4000])
    print(f"{res['passed']}/{res['total']} checks passed")
    if "file_total" in res:
        print(f"{res['file_passed']}/{res['file_total']} audio-file checks passed")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
