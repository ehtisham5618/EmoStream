# Browser playback diagnostics

**Problem reported:** the backend reported 25 FPS, but the picture in the browser stuttered and lagged.

**Outcome:** the stutter and most of the lag were in the browser client, not the engine. After the changes below, a real (headless) Chromium session against the L40S worker presents 23.9 frames per second with 76 % of frame intervals between 30 and 50 ms, and the voice-to-face delay fell from 2.6 s to 0.55 s over a Pakistan → US-East connection.

## How presentation was measured

Backend counters cannot see what reaches the screen, so two independent instruments were added.

1. **External hook** (`evaluation/benchmarks/browser_playback.py`). Headless Chromium is started with a fake microphone; before the page loads, `CanvasRenderingContext2D.drawImage` is wrapped so that every actual canvas draw is timestamped with `performance.now()`, and animation frames are counted. This works on any build of the client, including the old one, and does not trust the app.
2. **In-app telemetry** (`frontend/src/lib/player.ts`, "Playback diagnostics" panel). Every statistic is taken inside the `requestAnimationFrame` callback at the moment a frame is drawn. The canvas pipeline has no video element, so `requestVideoFrameCallback` does not apply; the animation-frame callback is the presentation event for a canvas.

Fields reported by the client (and saved by "Save diagnostics file", one row per half second):

| Field | Meaning |
|---|---|
| received / shown per second | Frames arriving over the WebSocket vs distinct frames drawn |
| interval median / 95 % / longest | Time between consecutive drawn frames |
| frame age median / 95 % | Arrival in the browser → drawn |
| buffer depth, playout delay, timeline moves | State of the jitter buffer |
| late / skipped / overflow / held | Frames dropped because they arrived after a newer one was shown; frames skipped to catch up; frames discarded because the buffer was full; refreshes where the due frame was missing |
| out of order / duplicate | Sequence problems |
| decode time | JPEG decode (`createImageBitmap`, off the main thread) |
| picture ahead of sound | Audio-video offset when an uploaded file is played |
| voice to face | Time from sending the audio that completes a frame to receiving that frame (network both ways + server) |
| server delay, server queue, frames skipped by the server | From the server's `stats` message |

Server-side, per stage: behaviour model, stitching, rendering, post-processing (`stages_ms`), frames generated, frames skipped, queue depth.

## Baseline behaviour

From the two recordings (see `browser_session_quality_analysis.md`): about 10.5 distinct frames per second, intervals alternating between 10–50 ms and 150–250 ms.

Reproduced under controlled conditions with a local stand-in server (`evaluation/benchmarks/fake_server.py`) that sends frames with the real engine's timing — groups of five, 20 ms apart — to the **old** client build in headless Chromium, 30 s:

| Old client | Regular delivery | Irregular delivery (8–58 ms per frame) |
|---|---|---|
| Canvas draws per second | 25.1 | 25.3 |
| Interval median | 3.5 ms | 3.8 ms |
| Interval 95th percentile | 186 ms | 208 ms |
| Intervals under 20 ms | 80 % | 80 % |
| Intervals over 80 ms | 19.5 % | 19.9 % |
| Intervals at 30–50 ms | 0.3 % | 0.0 % |
| Interval standard deviation | 78 ms | 74 ms |

All 25 frames per second were drawn, but four out of five were drawn within a few milliseconds of the previous one, where a 60 Hz display shows only the last. The visible result is one or two images per 200 ms block, which is the stutter.

## Root causes and fixes

| # | Cause | Evidence | Fix |
|---|---|---|---|
| P1 | Frames were drawn on arrival. The server emits five frames per speech-encoder block, so they arrive in bursts. | Table above; matches the recordings | `FramePlayer`: frames are decoded on arrival, held in a bounded buffer, and presented at `base + k × 40 ms` from the animation-frame loop |
| P2 | Microphone audio captured while the portrait was being prepared was queued and sent in one burst, so the server began seconds behind. | Real-browser test: voice-to-face 2,576 ms, 378 of 1,305 frames skipped by the server | The client discards audio captured before `ready` (`session.ts`) |
| P3 | Microphone audio was sent in 200 ms chunks. | Adds up to 200 ms before the server can start | 80 ms chunks |
| P4 | No policy for late or early frames. | Under sustained lateness the first version of the player froze; under a backlog it built seconds of delay | Explicit policy, below |

Checked and found **not** to be causes: base64 (frames are binary), synchronous image decoding (decode is asynchronous, median 3–5 ms), React re-renders (frames never pass through React state; statistics update twice a second), out-of-order or duplicate frames (none observed), extra canvas copies (one `drawImage` per frame).

### Presentation policy (`PlayoutClock` in `player.ts`)

- Target delay 120 ms for the microphone, 350 ms for an uploaded file; cap 600 ms; buffer at most 30 frames.
- A frame arriving after its slot: dropped the first time; if lateness repeats, the timeline moves later by the amount needed, as long as the total stays under the cap.
- If the source stays behind beyond the cap, the timeline is re-anchored on the current frame instead of freezing the picture.
- If frames arrive far ahead of the timeline (a backlog), the timeline jumps forward and the older frames are skipped, so delay cannot accumulate.
- If frames keep arriving with spare time, the timeline moves earlier one frame at a time.
- Uploaded audio: the timeline is locked to the audio clock and never moves; late frames are dropped. The sound starts exactly when frame 0 is shown.
- Every drop, skip, hold and timeline move is counted and displayed.

On the server, the existing bound stays: if a frame is already more than 450 ms old when its turn comes, rendering it is skipped (never more than two in a row) and the client holds the previous image.

## Measurements after the changes

### Local stand-in, same conditions as the baseline (headless Chromium, 30 s)

| New client | Regular delivery | Irregular delivery |
|---|---|---|
| Canvas draws per second | 25.0 | 24.3 |
| Interval median | 34.1 ms | 34.2 ms |
| Interval 95th / 99th percentile | 51.0 / 51.9 ms | 51.9 / 83.8 ms |
| Longest interval | 88 ms | 149 ms |
| Intervals under 20 ms | 0.1 % | 1.8 % |
| Intervals over 80 ms | 0.1 % | 2.1 % |
| Intervals at 30–50 ms | 81.5 % | 74.9 % |
| Interval standard deviation | 8.4 ms | 13.1 ms |

Intervals of 33 and 50 ms are the two nearest multiples of a 60 Hz refresh to the 40 ms frame period, so a 25 FPS stream on a 60 Hz display alternates between them; that is the expected best case.

### Real GPU worker (L40S, US-East), headless Chromium in Pakistan, 45 s

A 16 s recording with silent pauses, looped, played through Chromium's fake microphone device; model `it_ccc_la2`, per-frame streaming.

| | Before P2/P4 fixes | After |
|---|---|---|
| Frames drawn per second | 2.8 (picture stalled) | 23.9 |
| Interval median / 95th / 99th | — | 34.1 / 51.3 / 102.8 ms |
| Longest interval | 27 s | 533 ms (one event) |
| Intervals at 30–50 ms | — | 76.2 % |
| Intervals over 80 ms | — | 1.7 % |
| Voice to face (client) | 2,576 ms | 554 ms |
| Server delay, median | 285 ms | 252 ms |
| Frames skipped by the server | 378 of 1,305 | 11 of 1,241 |
| Frame age when shown, median / 95 % | 472 / 4,131 ms | 395 / 487 ms |
| Late / skipped / overflow / held (client) | 17 / 0 / 771 / 2,610 | 12 / 44 / 0 / 138 |
| Out of order / duplicate | 0 / 0 | 0 / 0 |

Of the 554 ms voice-to-face delay, about 250 ms is the server (200 ms of it is look-ahead the model needs) and about 300 ms is the two network legs. The client then holds frames for a further 270 ms on this connection (the buffer grew from its 120 ms target after repeated lateness); that is the price of even pacing on a long, jittery link.

Raw results: `docs/evaluation/data/browser_playback_local_*.json`, `browser_playback_gpu_l40s.json`.

## Limits of these measurements

- The browser was headless Chromium with a recording as the microphone. It exercises the real capture path (`getUserMedia` → audio worklet → WebSocket) but is not a person speaking into a real microphone on a visible display.
- One network path (Pakistan → US-East) and one 45-second session were measured. One 533 ms gap occurred; its cause was not isolated.
- A worker in a nearer region would remove most of the network share; that was not tested.
- Audio-video offset for uploaded files is instrumented but was not measured in this iteration.
- A five-minute browser session was not run; the five-minute stability result is engine-side (`final_iteration_report.md`).
