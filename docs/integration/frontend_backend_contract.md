# Frontend ↔ backend contract

This describes the backend **as implemented** on branch `iteration/animation-quality` (`backend/api/app.py`, `backend/streaming/protocol.py`, `backend/services/live.py`). A frontend that follows this document can drive the animation engine without changes to it. Nothing here is planned-only; anything not listed does not exist.

Reference client: `frontend/src/lib/` (`protocol.ts`, `session.ts`, `audio.ts`, `player.ts`). Reference test client: `evaluation/benchmarks/ws_client.py`.

## 1. Deployment facts

| | |
|---|---|
| Base URL | The Modal URL printed by `modal deploy modal/apps/serve.py` (HTTPS). The same origin serves the API, the WebSocket and the built frontend. |
| Authentication | None. The URL is unauthenticated. |
| Concurrency | **One live session per GPU worker.** A second session gets `busy`. |
| Cold start | The worker stops after 5 idle minutes. The first request afterwards waits for model loading (tens of seconds). `GET /api/info` can be used to wake it. |
| Session limit | 15 minutes of audio per session. |

## 2. HTTP endpoints

### `GET /api/health`
`{"status": "ok"}`. Does not touch the GPU.

### `GET /api/info`
```json
{
  "gpu": "NVIDIA L40S",
  "renderer": "tensorrt_fp16",
  "models": ["emostream", "ditto"],
  "emotions": ["neutral", "happy", "sad", "angry", "surprised"],
  "fps": 25,
  "sample_rate": 16000,
  "busy": false,
  "max_session_seconds": 900,
  "emostream_parameters": 1361385,
  "protocol": {"audio": "pcm_s16le mono", "frame": "jpeg", "video": ["jpeg", "h264"], "frame_period_ms": 40},
  "frontend_build": "20261117034200", "warm_up": {"ok": true, "register_s": 2.3, "first_frame_s": 0.6},
  "live_hop": 1, "live_slot": 4
}
```
`models` lists what the worker can actually run; `emostream` is absent if no trained checkpoint is loaded.

### `POST /api/export` — render an uploaded recording to MP4
`multipart/form-data`:

| Field | Type | Default | Notes |
|---|---|---|---|
| `portrait` | file | required | PNG, JPEG or WebP, ≤ 12 MB |
| `audio` | file | required | Any format ffmpeg reads, ≤ 30 MB; only the first 180 s are used |
| `emotion` | string | `neutral` | One of the five emotions |
| `intensity` | number | `1.0` | 0–1 |
| `model` | string | `emostream` | `emostream` or `ditto` |
| `size` | integer | `512` | 256, 384 or 512 |
| `portrait_consent` | boolean | `false` | Must be `true` |
| `audio_consent` | boolean | `false` | Must be `true` |

Success: `200`, `video/mp4` (H.264 + AAC, 25 FPS, watermarked), header `X-EmoStream-Stats: {"frames", "audio_s", "compute_fps"}`.

Errors (`{"detail": {"code", "message"}}`): `403 consent_required`; `409 busy`; `413 audio_too_large`; `422` with `bad_emotion`, `bad_intensity`, `bad_model`, `bad_size`, `bad_portrait`, `portrait_too_large`, `bad_audio`, `no_face`, `model_unavailable`.

Inputs are written to a temporary directory for the request and deleted before the response is sent.

## 3. Live session: `WS /ws/session`

One WebSocket = one session = one portrait. Text messages are JSON with a `type`. Binary messages start with a one-byte tag.

### 3.1 Sequence

```
client                                   server
  │── text  start ───────────────────────▶│  validates consent and options
  │── bin   0x10 + portrait bytes ───────▶│  detects the face, builds the avatar (≈1–4 s)
  │◀───────────────────────── text ready ─│
  │── bin   0x01 + PCM audio (repeat) ───▶│
  │◀──────── bin 0x02 + frame (repeat) ───│  one message per video frame
  │◀──────────────── text stats (~1/s) ───│
  │── text  emotion (any time) ──────────▶│
  │◀───────────────── text emotion_ack ───│
  │── text  end ─────────────────────────▶│  renders the remaining frames
  │◀─────────────────────────── text done │  then the client closes
```
Audio sent before `ready` is not accepted by the server; the reference client queues it and sends it once `ready` arrives.

### 3.2 Client → server

**`start`** (first message, text)
```json
{"type": "start",
 "consent": {"portrait": true, "audio": true},
 "sample_rate": 16000,
 "emotion": "neutral", "intensity": 1.0,
 "model": "emostream", "size": 512, "jpeg_quality": 80,
 "video": "h264", "bitrate_kbps": 900, "client_build": "20261117034200"}
```
- `client_build` (optional): the page's build identifier; echoed in `ready` for diagnostics.
- `consent.portrait` and `consent.audio` must both be the JSON value `true`. Anything else → `consent_required`, and no engine work is done.
- `sample_rate`: 16000, 22050, 24000, 32000, 44100 or 48000. **Send 16000.** Other rates are resampled per chunk on the server, which is lower quality.
- `size`: 256, 384 or 512 (square). `jpeg_quality`: 40–95.
- `video`: `"h264"` or `"jpeg"`. **Required for live sessions** since 17 Nov 2026: a start without it is refused with `client_outdated` (only the cached pre-H.264 page omitted it). **Send `"h264"`** when the browser has WebCodecs (`VideoDecoder`); it needs about a tenth of the bandwidth. `bitrate_kbps`: 200–4000, default 900; the server lowers it by itself on a poor link. `ready.session.video.codec` says what the server will actually send (it falls back to `"jpeg"` if H.264 is not available on the worker).

**Portrait** (second message, binary): byte `0x10` followed by the image file bytes (PNG, JPEG or WebP, ≤ 12 MB). One clearly visible face, looking at the camera. A closed mouth and neutral expression give the best result.

**Audio** (binary, repeated): byte `0x01` followed by signed 16-bit little-endian mono PCM at the declared rate.
- Any chunk size; even byte count; ≤ 2 MB per message. The reference client sends 80 ms (1,280 samples) for the microphone and 200 ms for files.
- The server counts samples. Video frame *k* covers samples `[640·k, 640·(k+1))` at 16 kHz, i.e. 40 ms. Timing never depends on when a chunk arrives.
- For a live microphone, send as captured. For a file, send at real-time pace (the reference client does) so latency figures stay meaningful.

**`emotion`** (text, any time after `ready`)
```json
{"type": "emotion", "emotion": "happy", "intensity": 0.7, "at_seconds": 3.2}
```
`at_seconds` is optional: the position in the audio stream at which the change starts. Without it the change starts at the end of the audio received so far (emotion messages are applied in order with the audio messages, even when audio is still waiting to be rendered). The change is cross-faded over 10 frames (400 ms). Frames already generated are not altered. Sending the same emotion with a new `intensity` is how intensity is updated.

**`ack`** (text, about five times a second): `{"type": "ack", "frames": 412}` — the number of video messages received so far. The server uses it to tell whether frames are queueing in the connection; without it there is no network pacing. Not answered.

**`ping`** (text, optional): `{"type": "ping", "t": 1234.5}` is answered at once with `{"type": "pong", "t": 1234.5}`; `t` is opaque to the server. Gives the client the network round trip.

**`keyframe`** (text, H.264 only): the decoder reported an error; the next video message will be a key frame.

**`end`** (text): no more audio. The server renders what remains (including a final partial frame) and replies `done`.

**`stop`** (text): abandon the session immediately; queued audio and frames are discarded. Closing the socket has the same effect.

### 3.3 Server → client

**`status`** (before `ready`): `{"type": "status", "stage": "initializing_portrait"}` — the portrait arrived and the face is being prepared (typically 0.5–2.5 s on a warm worker). A UI should show progress from the moment it connects; on a cold worker the connection itself can take 20–40 s.

**`ready`**
```json
{"type": "ready", "session": {
  "model": "emostream", "size": 512, "fps": 25, "emotion": "neutral", "intensity": 1.0,
  "portrait": {"mouth_open": true, "lip_open_ratio": 0.21, "mouth_closed_automatically": true},
  "algorithmic_delay_ms": [200, 200],
  "video": {"codec": "h264", "bitrate_kbps": 900},
  "frontend_build": "20261117034200", "client_build": "20261117034200"}}
```
- `frontend_build`: the page bundled with this server. A page whose own build differs should reload itself (`/api/info` reports the same value).
- `portrait.mouth_open`: the uploaded photo shows an open mouth. `mouth_closed_automatically`: the engine is closing it before animating. A UI should tell the user when `mouth_open` is true, because results are better with a closed-mouth photo.
- `algorithmic_delay_ms`: `[min, max]` wait for future audio that the chosen model needs before a frame can be produced, excluding compute and network.

**Video frame, `video: "h264"`** (binary): 10-byte header, then one H.264 access unit.

| Offset | Type | Meaning |
|---|---|---|
| 0 | u8 | `0x03` |
| 1 | u32 LE | frame index *k* |
| 5 | u32 LE | server latency in ms |
| 9 | u8 | flags; bit 0 set = key frame |
| 10 | bytes | H.264 Annex B, constrained baseline, no B-frames, parameter sets repeated in every key frame |

Decode with WebCodecs: `new VideoDecoder(...)`, `configure({codec: "avc1.42E01F", optimizeForLatency: true})` (no `description`, because the stream is Annex B), one `EncodedVideoChunk` per message with `timestamp = k × 40000` µs. Every message must be passed to the decoder in order, starting with a key frame; a key frame is sent at the start, every two seconds, after a bitrate change and on request. One picture comes out per message.

**Video frame, `video: "jpeg"`** (binary): 9-byte header, then a JPEG.

| Offset | Type | Meaning |
|---|---|---|
| 0 | u8 | `0x02` |
| 1 | u32 LE | frame index *k* (0-based, contiguous, increasing) |
| 5 | u32 LE | server latency in ms: arrival of the frame's last audio sample → frame encoded |
| 9 | bytes | JPEG image, `size`×`size`, with the "AI-generated" watermark |

The presentation time of frame *k* is `k × 40 ms` on the audio timeline. Indices may have gaps, for two reasons: the worker fell behind and skipped rendering (`frames_dropped`), or the connection was backing up and the server held frames back before encoding (`video.frames_skipped_for_network`). In both cases the client keeps showing the previous image. A client must present frames on a 40 ms timeline from a small buffer, not on arrival — see `frontend/src/lib/player.ts` and `docs/iterations/current_iteration/browser_playback_diagnostics.md`.

**`stats`** (about once a second)
```json
{"type": "stats", "frames": 250, "frames_dropped": 0, "audio_s": 10.0,
 "latency": {"n": 250, "p50_ms": 268.7, "p95_ms": 319.4, "max_ms": 420.7, "mean_ms": 271.1,
             "output_fps": 25.02, "max_frame_gap_ms": 163.6},
 "compute_fps": 45.1,
 "stages_ms": {"behaviour": 1.7, "stitch": 0.8, "render": 19.5, "post": 0.1},
 "gpu": {"torch_alloc_gib": 0.31, "torch_reserved_gib": 0.39},
 "queued_chunks": 0,
 "video": {"codec": "h264", "target_kbps": 900, "sent_kbps": 865.0, "frames_sent": 244,
           "frames_skipped_for_network": 6, "in_flight_frames": 9, "backlog_ms": 27, "congestion_events": 1},
 "uplink": {"lag_p95_ms": 96.0, "lag_max_ms": 158.0}}
```
| Field | Meaning |
|---|---|
| `frames` | Frames generated so far (including skipped ones) |
| `frames_dropped` | Frames the server skipped to bound delay |
| `audio_s` | Seconds of audio received |
| `latency.*` | Server-side audio-to-frame latency over the session |
| `latency.output_fps` | Frames produced per second on the server. **Not** the frame rate on screen. |
| `compute_fps` | Frames per second of pure compute time (headroom indicator) |
| `stages_ms` | Per-frame time: behaviour model (with speech encoder), stitching, rendering, post-processing |
| `gpu` | PyTorch memory; TensorRT memory is not included |
| `queued_chunks` | Audio chunks waiting on the server; a growing value means the worker is behind |
| `video.target_kbps` / `sent_kbps` | H.264 target after adaptation / bitrate actually sent over the last two seconds |
| `video.frames_skipped_for_network` | Frames held back because the client was falling behind |
| `video.backlog_ms` | Estimated time frames are spending queued in the connection (from `ack`) |
| `video.congestion_events` | Times the server started holding frames back and lowered the bitrate |
| `uplink.lag_*` | How late audio reached the server relative to the best case in the last five seconds; large values mean the client's upload is bursty |

**`emotion_ack`**: `{"type": "emotion_ack", "at_frame": 375, "emotion": "happy", "intensity": 0.7}` — the first frame the change applies to.

**`done`**: `{"type": "done", "stats": {…}}` — final statistics; same fields as the engine's `stats()` (a superset of the `stats` message, including `expected_frames`, `frames_rendered`, `emotion_changes`).

**`error`**: `{"type": "error", "code": "...", "message": "..."}`, after which the server closes the socket.

### 3.4 Error codes and recovery

| Code | When | What the client should do |
|---|---|---|
| `expected_start` | First message is not `start` | Programming error |
| `consent_required` | Either consent flag is not `true` | Ask the user to confirm; reconnect |
| `bad_sample_rate`, `bad_emotion`, `bad_intensity`, `bad_model`, `bad_size`, `bad_quality`, `bad_video`, `bad_bitrate` | Invalid option | Fix the value; reconnect |
| `expected_portrait` | Second message is not the portrait | Programming error |
| `bad_portrait`, `portrait_too_large` | Not an image, or over 12 MB | Ask for another file |
| `no_face` | No usable face found | Ask for a clearer, frontal photo |
| `model_unavailable` | `emostream` requested but no checkpoint on the worker | Offer `ditto`, or report |
| `busy` | Another session is using the worker | Retry after a few seconds |
| `bad_audio`, `audio_too_large`, `unexpected_binary` | Malformed audio message | Programming error |
| `session_too_long` | Over 15 minutes of audio | Start a new session |
| `bad_json`, `bad_message`, `unknown_type` | Malformed text message | Programming error |
| `client_outdated` | Start request without `video` (an old, cached page) | Reload the page |
| `overloaded` | More than two minutes of audio waiting on the server | Start a new session |
| `internal_error` | Unexpected server fault (logged in full on the worker) | Show the message; offer to start again |

There is no resume: after any error or disconnect, open a new socket and send `start` and the portrait again.

## 4. Consent and safety (enforced by the backend)

- A session or export cannot start without both consent flags. The engine itself refuses (`require_consent`), independently of the API layer.
- Every frame is watermarked inside the engine. There is no option to disable it.
- Portraits and audio are not stored. The portrait is written to a temporary file for decoding and deleted before `ready` is sent.

## 5. Client responsibilities

1. Capture microphone audio as 16 kHz mono (an `AudioContext` created with `sampleRate: 16000`), convert to PCM16.
2. Ask for `video: "h264"` when `VideoDecoder` supports `avc1.42E01F`, otherwise `"jpeg"`. Send `ack` five times a second.
3. Present frames on a 40 ms timeline from an adaptive buffer (`frontend/src/lib/player.ts`, `PlayoutClock`): place the timeline behind the 95th percentile of recent arrival lateness, move it later at once when a frame arrives after its slot, give delay back slowly.
4. **Play and record the voice on the picture's timeline.** Sample *n* of the audio that was sent belongs at `timeline base + n / 16000 s` (`frontend/src/lib/audio.ts`, `SyncedVoice`). A viewer, and any recording, must get the voice from there, never the live microphone, or the face will always appear to lag the voice by the whole round trip. Whether the speaker also hears it is a product choice (the test client offers a checkbox; headphones are needed).
5. For an uploaded file, play the audio locally and lock the picture to the audio clock.
6. Recording of a live session is done in the browser (`MediaRecorder` on the canvas plus the synced voice). Keep an inaudible source running on the recorded audio stream and repaint the canvas while a frame is held; otherwise Chrome's recorder loses step during pauses. The server only exports uploaded recordings.

## 6. What a future input method needs

Text-to-speech or a generated reply only has to produce mono PCM audio and feed it through the same `0x01` audio messages (or through `AvatarSession.push_audio` on the server). The engine has no dependency on where the audio comes from.
