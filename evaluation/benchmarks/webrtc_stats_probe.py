"""Reads the browser's own WebRTC receive statistics for a public demo call.

Opens a page in a fresh Chromium profile with a fake microphone, clicks a "start call"
control, and samples ``RTCPeerConnection.getStats()`` for the inbound video and audio.
Only media statistics are kept (codec, size, frame rate, bitrate, jitter-buffer delay);
no tokens, URLs with credentials, cookies or message bodies are read or written.

    python -m evaluation.benchmarks.webrtc_stats_probe --url https://keyframelabs.com --seconds 30
"""
from __future__ import annotations

import argparse
import json

HOOK = """
(() => {
  window.__pcs = [];
  const Orig = window.RTCPeerConnection;
  if (!Orig) return;
  window.RTCPeerConnection = function (...a) { const pc = new Orig(...a); window.__pcs.push(pc); return pc; };
  window.RTCPeerConnection.prototype = Orig.prototype;
  Object.setPrototypeOf(window.RTCPeerConnection, Orig);
})();
"""

SAMPLE = """
async () => {
  const out = [];
  for (const pc of window.__pcs || []) {
    if (pc.connectionState === 'closed') continue;
    const stats = await pc.getStats();
    const codecs = {};
    stats.forEach((s) => { if (s.type === 'codec') codecs[s.id] = s.mimeType; });
    stats.forEach((s) => {
      if (s.type === 'inbound-rtp') out.push({
        kind: s.kind, codec: codecs[s.codecId] || null, bytes: s.bytesReceived, t: s.timestamp,
        w: s.frameWidth, h: s.frameHeight, fps: s.framesPerSecond, decoded: s.framesDecoded,
        dropped: s.framesDropped, lost: s.packetsLost, packets: s.packetsReceived, jitter: s.jitter,
        jbDelay: s.jitterBufferDelay, jbEmitted: s.jitterBufferEmittedCount, jbTarget: s.jitterBufferTargetDelay,
        freezes: s.freezeCount, nack: s.nackCount, pli: s.pliCount, decoder: s.decoderImplementation,
      });
      if (s.type === 'candidate-pair' && s.nominated) out.push({ kind: 'pair', rtt: s.currentRoundTripTime });
    });
  }
  return out;
}
"""


def run(url: str, seconds: float, button: str, mic_wav: str | None, headed: bool, then: str = "") -> dict:
    import re

    from playwright.sync_api import sync_playwright

    args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required"]
    if mic_wav:
        args.append(f"--use-file-for-fake-audio-capture={mic_wav}")
    samples = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, args=args)
        ctx = browser.new_context(permissions=["microphone"], viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.add_init_script(HOOK)
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)
        names = [b.inner_text().strip()[:40] for b in page.get_by_role("button").all()[:40]]
        target = page.get_by_role("button", name=re.compile(button, re.I)).first
        target.scroll_into_view_if_needed(timeout=15000)
        target.click(timeout=15000)
        if then:
            page.wait_for_timeout(2500)
            page.get_by_role("button", name=re.compile(then, re.I)).first.click(timeout=15000)
        for _ in range(int(seconds)):
            page.wait_for_timeout(1000)
            samples.append(page.evaluate(SAMPLE))
        state = page.evaluate("""() => ({
          pcs: (window.__pcs || []).map((pc) => ({ state: pc.connectionState, ice: pc.iceConnectionState,
            receivers: pc.getReceivers().map((r) => r.track && r.track.kind + ':' + r.track.readyState) })),
          videos: [...document.querySelectorAll('video')].map((v) => ({ w: v.videoWidth, h: v.videoHeight,
            live: !!v.srcObject, paused: v.paused, t: v.currentTime })),
          buttons: [...document.querySelectorAll('button')].map((b) => b.innerText.trim().slice(0, 30)).filter(Boolean).slice(0, 12),
        })""")
        browser.close()
    video = [[s for s in snap if s.get("kind") == "video"] for snap in samples]
    video = [v[0] for v in video if v]
    audio = [[s for s in snap if s.get("kind") == "audio"] for snap in samples]
    audio = [a[0] for a in audio if a]
    rtt = [s["rtt"] for snap in samples for s in snap if s.get("kind") == "pair" and s.get("rtt") is not None]
    out: dict = {"buttons_seen": names, "snapshots": len(samples), "video_snapshots": len(video),
                 "last_snapshot": samples[-1] if samples else None, "page_state": state}
    if len(video) >= 2:
        a, b = video[0], video[-1]
        dt = (b["t"] - a["t"]) / 1000
        out["video"] = {
            "codec": b["codec"], "width": b["w"], "height": b["h"], "decoder": b["decoder"],
            "fps_reported": [v["fps"] for v in video][-10:],
            "frames_per_second_mean": round((b["decoded"] - a["decoded"]) / dt, 2) if dt else None,
            "bitrate_kbps": round((b["bytes"] - a["bytes"]) * 8 / dt / 1000, 1) if dt else None,
            "packets_lost": b["lost"], "frames_dropped": b["dropped"], "freezes": b["freezes"],
            "nack": b["nack"], "pli": b["pli"],
            "jitter_buffer_ms_mean": round(1000 * (b["jbDelay"] - a["jbDelay"]) / max(1, b["jbEmitted"] - a["jbEmitted"]), 1),
            "seconds": round(dt, 1),
        }
    if len(audio) >= 2:
        a, b = audio[0], audio[-1]
        dt = (b["t"] - a["t"]) / 1000
        out["audio"] = {
            "codec": b["codec"], "bitrate_kbps": round((b["bytes"] - a["bytes"]) * 8 / dt / 1000, 1) if dt else None,
            "jitter_buffer_ms_mean": round(1000 * (b["jbDelay"] - a["jbDelay"]) / max(1, b["jbEmitted"] - a["jbEmitted"]), 1),
        }
    if rtt:
        out["rtt_ms_median"] = round(1000 * sorted(rtt)[len(rtt) // 2], 1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--button", default="start call|talk|try")
    ap.add_argument("--mic-wav", default=None)
    ap.add_argument("--then", default="", help="second control to click after the first")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    res = run(a.url, a.seconds, a.button, a.mic_wav, a.headed, a.then)
    print(json.dumps(res, indent=1))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)
