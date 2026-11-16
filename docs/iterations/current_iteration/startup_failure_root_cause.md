# Startup failures: root cause and fix

Date: 17 November 2026. Evidence: Modal worker log of the user's session of 16 November, 21:47–21:49 (Pakistan time), workspace `abdulmat40`, app `emostream-v2-live`, L40S.

## What the user saw

Pressing Start produced an error several times; a later attempt started and played.

## What the worker log shows

| Time (UTC) | Event |
|---|---|
| 16:47:16–16:47:37 | Container cold start: image load, Ditto modules compiled, face models and TensorRT engines loaded. First `GET /api/info` took 21.2 s |
| ~16:47:45 | First session: portrait registered, first audio processed |
| shortly after | **`KeyError: 'ms_per_frame'`** in `backend/api/app.py` (statistics message); session task crashed; socket closed (`CONNECT /ws/session … 19.0 s`) |
| ~16:48:11 | Second attempt: same `KeyError`, same crash (`12.5 s`) |
| ~16:48:59 | Third attempt: ran for 60 s (the session in `emostream-session (4).webm`) |

`libonnxruntime_providers_cuda.so … libcublasLt.so.11` errors and ONNX "Expected shape … does not match" warnings appear at every start. They come from the face-detection models falling back to CPU and from dynamic shapes. They are harmless and occur in the successful session too, so they are **not** the cause.

## Root cause

`StageTimer.summary(n_frames)` added `ms_per_frame` to a stage only when `n_frames` was non-zero. The WebSocket handler sends a statistics message once a second and read `v["ms_per_frame"]` for every stage. If one second passed after `ready` before the first frame was finished, the dictionary had no such key, and the handler crashed.

That condition holds exactly on a freshly started worker: the first audio triggers lazy initialisation (speech encoder, first TensorRT and CUDA calls), so no frame exists one second in. Once those had happened, later sessions produced frames within the first second and did not crash. Hence the user saw "fails a few times, then works".

The crash was also reported badly. The exception escaped the handler, the socket closed without an `error` message, and the page could only say "The connection to the server failed."

## Contributing problem: an old page against a new server

The diagnostics file of that session has no `codec`, `jitterP95Ms` or network fields, and the server statistics report codec `jpeg` with no acknowledgements received. The browser was running the page from before the H.264 change: it had been cached. With the old page, none of the transport fixes were in effect.

## Fixes

| Problem | Fix | Where |
|---|---|---|
| Crash on statistics before the first frame | `ms_per_frame` is always present (`None` until a frame exists); the handler reads it with `.get` | `emostream/telemetry.py`, `backend/api/app.py` |
| First session pays for lazy initialisation | The worker runs a 2-second throw-away session on Ditto's example portrait before serving (measured: portrait 1.8 s, first frame 0.24 s, 3.2 s in total) | `GpuEngineProvider.warm_up`, `modal/apps/serve.py` |
| Faults closed the socket silently | Any unexpected exception is logged with its traceback and sent to the client as `{"type": "error", "code": "internal_error"}`; the worker slot is released | `backend/api/app.py` |
| No visible progress during start-up | The server sends `{"type": "status", "stage": "initializing_portrait"}`; the page shows "Connecting…", "Starting the avatar server…" (after 5 s, with seconds counted), "Preparing your portrait…" | `backend/api/app.py`, `frontend/src/lib/session.ts`, `App.tsx` |
| Stale page | The page is served with `Cache-Control: no-store`. Every build writes an identifier to `build.json`; `/api/info` reports it, and a page with a different identifier reloads itself once | `frontend/vite.config.ts`, `backend/api/app.py`, `App.tsx` |
| Unbounded audio queue on the server | At most 1,500 audio messages (two minutes) queued; beyond that the client gets `overloaded` instead of the queue growing | `backend/api/app.py` |
| Audio captured before ready | Already discarded by the client since the previous iteration (not queued, not sent) | `frontend/src/lib/session.ts` |

## Tests

New unit tests: statistics with zero frames; progress message before `ready`; an engine fault becomes an `internal_error` message and frees the worker; the audio queue limit. All 80 Python and 11 frontend tests pass.

Deployed worker, 17 November:

| Check | Result |
|---|---|
| Cold start to first `/api/info` answer (includes warm-up) | 36 s |
| Warm-up session | OK: portrait 1.78 s, first frame 0.24 s |
| `Cache-Control` on `/` | `no-store, max-age=0` |
| Three consecutive browser sessions (headless Chromium, recorded speech as the microphone, 20 s each) | 3 of 3 started without error; first frames 6.5, 4.7, 4.2 s after Start; 24.9–25.2 frames per second drawn |

Not tested: a WebSocket cut in the middle of a session (the page reports it and returns to idle; no automatic reconnect), and Start pressed while the worker is still cold from a person's own browser.
