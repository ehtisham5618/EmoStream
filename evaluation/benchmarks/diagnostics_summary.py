"""Summarises one or more "Save diagnostics file" exports from the browser client.

    python -m evaluation.benchmarks.diagnostics_summary emostream-diagnostics.json ...
"""
from __future__ import annotations

import json
import sys


def summarise(path: str) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    rows = d["rows"]
    live = [r for r in rows if r["client"]["received"] > 0]
    first, last = live[0], live[-1]
    c = last["client"]
    srv = [r["server"] for r in live if r.get("server")]
    s = srv[-1] if srv else {}
    trips = [r["roundTripMs"] for r in live if r.get("roundTripMs") is not None]
    secs = (last["t"] - first["t"]) / 1000
    out = {
        "file": path.split("/")[-1].split("\\")[-1],
        "client_build_fields": "new (H.264 client)" if "codec" in c else "old (JPEG-only client)",
        "seconds_waiting_before_first_frame": round((first["t"] - rows[0]["t"]) / 1000, 1),
        "seconds_with_frames": round(secs, 1),
        "frames_received": c["received"], "frames_shown": c["presented"],
        "shown_per_second": round(c["presented"] / secs, 1) if secs else None,
        "dropped_late": c["droppedLate"], "skipped_catch_up": c["skipped"], "holds": c["holds"],
        "timeline_moves": c["timelineShifts"], "longest_gap_ms": max(r["client"]["intervalMaxMs"] or 0 for r in live),
        "voice_to_frame_arrival_ms": {"min": round(min(trips)), "max": round(max(trips)), "last": round(trips[-1])} if trips else None,
        "server_codec": (s.get("video") or {}).get("codec", "jpeg (field absent)"),
        "server_sent_kbps_max": max(((r.get("video") or {}).get("sent_kbps") or 0) for r in srv) if srv else None,
        "server_latency_p50_p95_max": [s.get("latency", {}).get(k) for k in ("p50_ms", "p95_ms", "max_ms")],
        "server_output_fps": s.get("latency", {}).get("output_fps"),
        "server_frames_dropped": s.get("frames_dropped"), "server_frames": s.get("frames"),
        "uplink_lag_max_ms": max(((r.get("uplink") or {}).get("lag_max_ms") or 0) for r in srv) if srv else None,
        "ack_seen_by_server": any(((r.get("video") or {}).get("in_flight_frames", 0) or 0) < ((r.get("video") or {}).get("frames_sent", 0) or 0) for r in srv),
    }
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(summarise(p), indent=1))
