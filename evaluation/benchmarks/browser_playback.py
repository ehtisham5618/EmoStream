"""Measures what a real browser actually presents during a live session.

Opens the EmoStream page in headless Chromium with a fake microphone, starts a session,
and records the time of every canvas draw (by wrapping ``drawImage`` before the page
loads) together with every animation frame. The numbers therefore describe frames that
reached the screen, independent of any counter kept by the app or the server.

    # against the local timing stand-in
    python -m evaluation.benchmarks.fake_server --dist frontend/dist --port 8765 &
    python -m evaluation.benchmarks.browser_playback --url http://127.0.0.1:8765 --seconds 30

    # against a deployed GPU worker, speaking a WAV file through the fake microphone
    python -m evaluation.benchmarks.browser_playback --url https://<app>.modal.run \
        --portrait portrait.png --mic-wav speech48k.wav --seconds 30
"""
from __future__ import annotations

import argparse
import io
import json
import time

import numpy as np

HOOK = """
(() => {
  window.__draws = [];
  window.__rafs = 0;
  const orig = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (...a) {
    // a canvas drawn onto itself is the player keeping a held picture alive, not a new frame
    if (!(a[0] instanceof HTMLCanvasElement)) window.__draws.push(performance.now());
    return orig.apply(this, a);
  };
  const tick = () => { window.__rafs++; requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
})();
"""


def summarise(draws: list[float], seconds: float, rafs: int) -> dict:
    t = np.asarray(draws, dtype=np.float64)
    if len(t) < 3:
        return {"draws": int(len(t))}
    t = t[t > t[0] + 1000]            # skip the first second (start-up)
    d = np.diff(t)
    span = (t[-1] - t[0]) / 1000
    return {
        "draws": int(len(t)), "seconds_measured": round(float(span), 2),
        "presented_fps": round(float((len(t) - 1) / span), 2),
        "interval_ms": {"p5": round(float(np.percentile(d, 5)), 1), "p50": round(float(np.percentile(d, 50)), 1),
                        "p95": round(float(np.percentile(d, 95)), 1), "p99": round(float(np.percentile(d, 99)), 1),
                        "max": round(float(d.max()), 1)},
        "intervals_within_30_to_50_ms": round(float(((d >= 30) & (d <= 50)).mean()), 3),
        "intervals_under_20_ms": round(float((d < 20).mean()), 3),
        "intervals_over_80_ms": round(float((d > 80).mean()), 3),
        "interval_std_ms": round(float(d.std()), 1),
        "display_refresh_hz": round(rafs / max(seconds, 1e-6), 1),
    }


def run(url: str, portrait: str | None, mic_wav: str | None, seconds: float, emotion: str | None, headed: bool,
        shots: str = "", record: str = "") -> dict:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    if portrait is None:
        buf = io.BytesIO()
        Image.new("RGB", (256, 256), (150, 120, 100)).save(buf, "PNG")
        portrait_payload = {"name": "portrait.png", "mimeType": "image/png", "buffer": buf.getvalue()}
    else:
        portrait_payload = portrait
    args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"]
    if mic_wav:
        args.append(f"--use-file-for-fake-audio-capture={mic_wav}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, args=args)
        ctx = browser.new_context(permissions=["microphone"], accept_downloads=True)
        page = ctx.new_page()
        page.add_init_script(HOOK)
        logs = []
        page.on("console", lambda m: logs.append(m.text) if m.type in ("error", "warning") else None)
        page.goto(url, wait_until="networkidle", timeout=180000)
        page.set_input_files('input[type="file"][accept*="image"]', portrait_payload)
        for box in page.locator('input[type="checkbox"]').all():
            box.check()
        if emotion:
            page.get_by_role("radio", name=emotion, exact=True).click()
        clicked = time.time()
        page.get_by_role("button", name="Start speaking").click()
        page.wait_for_function("() => window.__draws.length > 5 || !!document.querySelector('p.error')", timeout=240000)
        startup_error = page.locator("p.error").inner_text() if page.locator("p.error").count() else None
        if startup_error:
            browser.close()
            return {"startup_error": startup_error, "seconds_to_error": round(time.time() - clicked, 1)}
        seconds_to_first_frames = round(time.time() - clicked, 1)
        raf0 = page.evaluate("() => window.__rafs")
        t0 = time.time()
        if shots:
            import os

            os.makedirs(shots, exist_ok=True)
            n = max(1, int(seconds // 3))
            for i in range(n):
                page.wait_for_timeout(int(seconds * 1000 / n))
                page.locator("canvas").screenshot(path=os.path.join(shots, f"shot_{i:02d}.png"))
        else:
            page.wait_for_timeout(int(seconds * 1000))
        draws = page.evaluate("() => window.__draws")
        rafs = page.evaluate("() => window.__rafs") - raf0
        elapsed = time.time() - t0
        # the app's own diagnostics panel, if this build has one
        app_stats = None
        if page.locator("details.diag").count():
            page.locator("details.diag summary").click()
            app_stats = page.locator("details.diag dl").inner_text()
        numbers = page.locator("dl.numbers").inner_text() if page.locator("dl.numbers").count() else None
        logs_js = page.evaluate("""() => {
          const e = window.__emostream; if (!e) return null;
          const v = e.voice();
          return { shown: e.player.shownLog, played: v ? v.playedLog : [], scheduled: v ? v.scheduled : 0, missed: v ? v.missed : 0 };
        }""")
        if record:
            page.wait_for_timeout(300)
        page.get_by_role("button", name="Stop").click()
        page.wait_for_timeout(2500)
        if record and page.locator("a[download='emostream-session.webm']").count():
            # the session recording the user would save: picture plus the avatar's voice
            with page.expect_download() as dl:
                page.locator("a[download='emostream-session.webm']").click()
            dl.value.save_as(record)
        browser.close()
    out = summarise(draws, elapsed, rafs)
    if logs_js and logs_js["played"] and logs_js["shown"]:
        # Picture minus sound, per drawn frame: when frame k was drawn vs when sample 640 k was played.
        import bisect

        played = sorted(logs_js["played"])
        firsts = [p[0] for p in played]
        diffs = []
        for k, t_draw in logs_js["shown"]:
            i = bisect.bisect_right(firsts, k * 640) - 1
            if i < 0:
                continue
            first, at = played[i]
            if k * 640 - first > 16000 * 0.3:
                continue                                  # that audio was not played (missed chunk)
            diffs.append(t_draw - (at + (k * 640 - first) / 16))
        if diffs:
            d = np.asarray(diffs)
            out["picture_minus_sound_ms"] = {"p5": round(float(np.percentile(d, 5)), 1), "p50": round(float(np.median(d)), 1),
                                             "p95": round(float(np.percentile(d, 95)), 1), "n": int(len(d)),
                                             "within_80_ms": round(float((np.abs(d) <= 80).mean()), 3)}
        out["voice_chunks"] = {"scheduled": logs_js["scheduled"], "missed": logs_js["missed"]}
    out["startup_error"] = None
    out["seconds_to_first_frames"] = seconds_to_first_frames
    out["app_diagnostics"] = app_stats
    out["app_numbers"] = numbers
    out["console_errors"] = logs[:10]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--portrait", default=None)
    ap.add_argument("--mic-wav", default=None, help="48 kHz WAV played as the microphone")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--emotion", default=None)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--shots", default="", help="folder for canvas screenshots every ~3 s")
    ap.add_argument("--record", default="", help="save the app's own session recording (.webm) here")
    a = ap.parse_args()
    res = run(a.url, a.portrait, a.mic_wav, a.seconds, a.emotion, a.headed, a.shots, a.record)
    print(json.dumps(res, indent=1))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)
