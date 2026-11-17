# Lovable product UI integration — 17 November 2026

Branch `iteration/lovable-ui-integration`, created from `155f3e2` (live model `ph_aug`, approved). Not pushed.

## 1. Summary

The Lovable-generated product UI is now the EmoStream front end. It is served by the live worker at `/`, and its Studio drives the real engine: portrait with consent, microphone, live H.264 video on the stage, five emotions with intensity, the avatar's voice in step with the lips, telemetry, a diagnostics file, and export of the take. The design is unchanged except where the brief required real behaviour or honest content (sections 7–8). The engine, model (`ph_aug`), renderer, transport and 69-dimension motion representation are untouched. The test and diagnostics client moved to `/diagnostics/`.

Deployed: `https://abdulmat40--emostream-v2-live-web.us-east.modal.run` (Modal profile `abdulmat40`, app `emostream-v2-live`, NVIDIA L40S).

## 2. Source

`C:\Users\ehtis\Downloads\EmoStream_UI\task-finish-companion-main` (folder). Copied unchanged into `web/` and committed as delivered, so every later change is a reviewable diff. The original folder was not modified.

## 3. What the delivered UI was

- TanStack Start 1.168 (server-side rendering, nitro build targeting Cloudflare Workers), React 19, Tailwind 4, Radix/shadcn components, lucide icons, recharts, sonner. Fonts: Instrument Serif, Onest, IBM Plex Mono. Light and dark themes.
- Public site (`/`, `/how-it-works`, `/capabilities`, `/research`, `/responsible-ai`, `/privacy`, `/about`, `/sign-in`) and the app shell `/app/*`: Overview, Studio, My Avatars, Sessions, Analytics, Integrations, Models & Performance, Settings, About & Help, Text to speech and AI conversation (both marked "soon").
- No Supabase, database, authentication or third-party API calls. `lovable-error-reporting.ts` forwards errors only to hooks that exist inside the Lovable editor; outside it, it does nothing and makes no network request. It was kept.
- Its engine adapter assumed a protocol that does not exist:
  - a base64 portrait inside JSON;
  - untagged audio;
  - frames decoded as images;
  - stats fields the server does not send;
  - a JSON `/api/export`.

  Its microphone path also had problems: it started before the engine was ready, and it downsampled by picking every n-th sample (aliasing) in a ScriptProcessor.
- Content problems:
  - Seven invented sessions on the Sessions page.
  - Synthetic charts on Analytics:
    - an FPS trace;
    - a latency histogram shaped to 269/319 ms;
    - frame delivery;
    - a confusion matrix constructed to give F1 0.651.
  - Validation figures of the earlier model `reg` presented as current.
  - "HuBERT" named as the speech encoder.

## 4. Build strategy

The worker is a FastAPI app serving static files, so the UI is built with TanStack Start's **SPA mode**: one prerendered `index.html`, client-side routing, no server runtime (`nitro: false`). The TanStack/Lovable setup was kept, so components, routing and styling are exactly the delivered ones. Output: `web/dist/client`.

`scripts/build_frontends.sh` builds `web/` and `frontend/` (with base `/diagnostics/`) using one build identifier (`EMOSTREAM_BUILD`). It fails if the identifiers differ or if the diagnostics assets are not under `/diagnostics/`.

## 5. Layout

```
web/                 product UI (Lovable design)            → served at /
frontend/            test and diagnostics client            → served at /diagnostics/
frontend/src/lib/    the engine client (protocol, session, player, audio), imported by web/ as @engine/*
scripts/build_frontends.sh
```

There is one implementation of the wire protocol. The shared files received type-only changes (non-null assertions, bracket property access) so that they compile under web/'s stricter TypeScript settings, plus two optional parameters: `LiveSession.open(…, url)` and `startMicrophone(…, {deviceId})`. Runtime behaviour of the diagnostics client is unchanged.

## 6. Connection to the engine

| Studio action | On the wire (contract unchanged) |
|---|---|
| Start session | Microphone permission asked first (no GPU session is opened if refused). Then WebSocket `/ws/session` on the page's origin, `start` with `consent {portrait, audio}`, `video: "h264"` (JPEG if WebCodecs is missing), intensity ÷ 100, `client_build`. Then `0x10` + the cropped portrait as JPEG bytes (up to 1024 px, never upscaled) |
| Startup | `status: initializing_portrait` and connection time shown on the stage with elapsed seconds; cold-start message after 8 s |
| Ready | Microphone opens now (AudioWorklet, 16 kHz, chosen device); 80 ms chunks as `0x01` PCM16. Nothing is captured or sent before `ready`. Open-mouth portraits get the engine's notice |
| Video | `0x03` H.264 → `FramePlayer` (WebCodecs, adaptive jitter buffer, 40 ms timeline) drawing on the stage canvas. `ack` 5×/s, `ping` 1×/s, `keyframe` on decoder errors |
| Emotion, intensity | `emotion` messages, intensity 0–1, debounced 120 ms; `emotion_ack` received |
| Hear the avatar's voice | `SyncedVoice` monitor gain: the sent audio, played at the picture's timeline; headphone advice next to the switch. The context is created inside the Start click (autoplay rules); the microphone is never routed to the speakers (no double playback) |
| Pause / Resume | No audio sent while paused (the last partial chunk is flushed first); the picture holds |
| Stop | Remaining audio, `end`, wait for `done`, play out the buffer, close |
| Audio file (Voice → "Audio file") | The clip is decoded to 16 kHz before the session opens (the microphone is never requested), then sent from `ready` at speaking pace in 200 ms chunks, played locally from the moment frame 0 is shown, and the picture is locked to the playback clock (`FramePlayer` synced mode). The take ends by itself (`end` → `done`). Pause stops the feed and suspends playback |
| Export | Microphone takes: the browser's recording (canvas + synced voice, WebM). Audio-file takes: **Export MP4**, rendered by the engine from the same portrait crop and the file (`POST /api/export`, multipart, both consents, the emotion the take started with, first 180 s); the WebM stays available as a second download |
| Errors | Engine codes mapped to plain messages (`busy`, `no_face`, `client_outdated`, `session_too_long`, …); connection loss → "Connection lost" with Reconnect |

Engine address: empty by default, which means the page's own origin. `VITE_ENGINE_URL` can set it at build time, and Settings can override it. The production URL is not written in any component. No secrets or tokens exist on the client side.

## 7. Studio changes visible to the user

Each change below uses the delivered components and styles:

- **Voice consent** checkbox next to the portrait consent, in the same style. Start requires both.
- **"Hear the avatar's voice"** switch with headphone advice.
- **Telemetry drawer**: the delivered row kept, with real values.
  - FPS = pictures drawn per second on this screen.
  - Server latency (median), RTT, frames received, displayed and lost.
  - Peak VRAM shows "—": the engine does not report TensorRT memory per session.

  A second row was added: voice ↔ lips offset, share within 80 ms, avatar delay, server p95, video bitrate and codec, startup time, frames skipped by server and network, and uplink lag. Also added: **Save diagnostics file**.
- **Audio file** tab (added 17 Nov, at the user's request; it was a coming-soon dialog in the delivered design): file picker in the style of the portrait drop area, file name, duration and size, replace; consent text worded for a recording; level meter, waveform and timeline driven by the audio being sent; "Export MP4" plus a WebM link after the take. Sessions shows the take's input source.
- Removed: the 450 ms artificial "preparing" delay after upload, and the "preview" mode (microphone running with no engine).
- Stage overlays show the real startup stage; the bottom strip says "Not streaming" instead of "Engine off".

## 8. Pages and honesty of content

- **Sessions**: the library (search, filters, sort, detail sheet, delete) now works on the real takes from this tab. Nothing is stored, by design.
- **Analytics**: tiles carry measured figures, each labelled with model and date:
  - engine figures from the 15 Nov L40S run, model `reg`;
  - quality figures for the live `ph_aug`: emotion F1 0.777, ArcFace 0.876, SyncNet LSE-C 5.08, mouth-opening correlation 0.600, /p b m/ precision 0.72;
  - live frame delivery: 1 of 688 skipped.

  The charts are drawn from your own takes: pictures per second, per-frame server latency from the video headers, frames per second, and intensities. Before a take they show an empty state. The confusion matrix was replaced by the measured validation history (`reg` → `it_ccc_la2` → `wl_base` → `ph_aug`, plus real video).
- **Home, Overview, Research, Models, Help**: same layout, figures relabelled as above. Speech encoder corrected to WavLM. Parameter count corrected to ≈1.30 M, computed from the architecture at WavLM's 768-d input; `/api/info` reports the exact count.
- **Integrations**: only the engine session API is "Available"; Meet, Zoom, Teams, LiveKit, WebRTC, SDK, TTS and LLM remain labelled planned or soon. **Text to speech** and **AI conversation** are unchanged and marked "soon".
- RTX 4050: "Not yet verified" everywhere; no claim is made.
- `web/src/lib/demo-data.ts` was deleted; nothing references demo or illustrative data any more.

## 9. Safety

Portrait and voice consent are required: in the UI, and also by the engine (unchanged). The "AI-generated" watermark is on every engine frame (unchanged) and also on the stage. Portraits stay in browser memory and are sent only during a session; the engine does not store them (unchanged). There is no voice cloning. No credentials appear in the bundles (only `VITE_*` variables are injected; none is set).

## 10. Backend changes (minimal, isolated)

`backend/api/app.py`, static serving only:

- `create_app(provider, static_dir, diagnostics_dir=None)`.
- `/` and every extension-less path (client routes) → `index.html`; existing files are served as they are.
- `/api/*`, `/ws/*` and missing assets return 404 and never the page.
- `/diagnostics/` serves the diagnostics client.
- Pages and `build.json` keep `Cache-Control: no-store`.
- GET and HEAD.

`modal/apps/serve.py` adds `web/dist/client` to the image. API, WebSocket, engine and settings (`ph_aug`, L40S, emotion gain 1.5, 1,000 ms latency bound, 6 s warm-up) are unchanged. The stale-page protection was kept: the page reloads once when the server's `frontend_build` differs (`BuildCheck`).

## 11. Tests (local, Windows, Node 24, Python 3.14)

| Suite | Result |
|---|---|
| `python -m pytest tests` | 100 passed (new: product UI + diagnostics serving, HEAD, no fallback for API paths) |
| `web/` vitest | 22 passed (consents, start message with both consents and intensity 0–1, engine address default, error messages, voice-lips offset, figures match their reports) |
| `frontend/` vitest | 11 passed |
| `tsc --noEmit` web / frontend | 0 errors / 0 errors |
| `eslint` web | 0 errors, 10 warnings (react-refresh notes in delivered UI files) |
| Production builds | both succeed; shared build id verified |

Prettier was applied to `web/` as a separate whitespace-only commit; the delivered files already failed it.

## 12. Browser end-to-end (`evaluation/benchmarks/studio_e2e.py`)

Headless Chromium drives `/app/studio` with a fake microphone and checks behaviour at the WebSocket message level. 18 checks:

1. Page served, not cached.
2. Start disabled without a portrait.
3. Upload.
4. Both consents required.
5. `status` before `ready`, zero audio before `ready`.
6. Start message contents.
7. No burst: first messages are 80 ms chunks, 13 in the first second.
8. H.264 frames drawn on the stage.
9. Live chip and watermark.
10. Avatar voice scheduled.
11. Emotion and intensity (1.0 at 100 %) sent and acknowledged.
12. Pause sends nothing, resume sends again.
13. `end` → `done` → complete.
14. Export file.
15. Diagnostics file.
16. Sessions and Analytics show the take; per-second counts plausible across pause/resume.
17. No console errors.

Route checks also fetch every script each page loads.

| Where | Result |
|---|---|
| Local timing stand-in (`fake_server.py`, no GPU) | 18/18 |
| Deployed L40S worker, your `Portrait.png`, your `Recording.wav` as microphone | 18/18 in each of 3 runs |

Deployed measurements (3 runs, about 24 s each including a 2.5 s pause):

| Measure | Values |
|---|---|
| Click → engine ready | 2.2 s, 1.7 s, 1.5 s (warm worker) |
| Click → first frame | 3.2 s, 2.7 s, 2.5 s |
| Server frames / skipped | 528 / 3, 529 / 3 |
| Server latency p50 / p95 | 208 / 327 ms, 207 / 362 ms |
| Pictures drawn per second (window includes the pause) | 21.7, 20.7 |
| Voice ↔ lips within 80 ms | 96.7 %, 79.5 %, 94.7 % (median offset 9–11 ms) |

In the third run the out-of-tolerance frames were spread across the take, not concentrated at pause/resume. The worse second run is not explained; network variation on this connection is the likely cause, but that is not verified.

**Audio-file take** (`--audio-file`, 9 checks: tab and file gating; no audio before `ready` and 200 ms chunks at speaking pace; frames drawn and the take ending by itself with `end`/`done`; microphone never requested; picture within 80 ms of the playback clock; Export MP4 is a real MP4; WebM also available; Sessions shows "Audio file"; no console errors). Local stand-in: 9/9 (its MP4 is an ffmpeg stand-in: solid picture + the audio). Deployed L40S, 10 s of your recording: 9/9 in two runs; picture offset to the playback clock −32 and −2 ms; the MP4 is 512×512 H.264 + AAC, 10.0 s, your portrait with the "AI-generated" label (checked by eye on a frame), 1.2 MB.

The first run after a fresh deployment failed checks 08 and 11: first frame 9.8 s after the click, 27 frames, no emotion acknowledgement; the first session on a new container was slow. The next runs on the same container passed. The two later microphone runs: voice and lips within 80 ms for 85.3 % and 94.8 % of frames, 553 and 550 frames with 3 skipped each.

Regression: the diagnostics client at `/diagnostics/` on the deployed worker gave 24.6 pictures per second, 94.7 % within 80 ms, no errors.

Not tested: a cold start through the new UI (the worker was warm), Firefox and Safari, a real person with a real microphone, mobile devices (only phone-width rendering, section 13), long sessions.

## 13. Visual comparison (`evaluation/benchmarks/ui_visual_compare.py`)

The delivered commit was run with `vite dev` and the integrated build on the local server. Full-page screenshots were taken of all 19 routes at 1440 px and 390 px, in light and dark (76 pairs). The share of pixels differing by more than 24 levels:

- **Unchanged content**: 0.00 % on capabilities, privacy, sign-in, responsible-ai, avatars (phone), integrations (phone), text-to-speech (phone) and conversation (phone). 0.03–0.2 % on avatars, integrations, text-to-speech, conversation, settings and about (desktop), from the engine-status dot and one corrected number. The how-it-works page differs by 0.07–0.08 % (the encoder name). One responsible-ai capture showed 8 %; it was 0.00 % on re-capture, a timing artefact.
- **Intended content changes**: Studio (added controls lengthen the Voice panel and the telemetry drawer), Sessions, Analytics, Models, Overview, Research, Home and Help differ, and later content moves down. The side-by-side images were reviewed: same typography, colours, spacing, components and layout.

## 14. Deployment

- `MODAL_PROFILE=abdulmat40 modal deploy modal/apps/serve.py`, after the local tests passed. Deployed twice: the first deployment exposed a build-script bug (Git Bash rewrote `/diagnostics/` into a Windows path, so the diagnostics page loaded no script), which was fixed, guarded in the build script and the route checks, and redeployed.
- No volumes, secrets or apps were deleted.
- GPU use: about 15 minutes of L40S for the browser tests, below $1 (estimated from minutes).

## 15. Known limitations

- Export downloads the browser's WebM recording, not an MP4 rendered by the engine.
- The MP4 export uses one emotion setting (the one the take started with); emotion changes made during the live take are only in the WebM recording. It renders the first 180 s.
- Peak GPU memory per session is not reported.
- Sessions and Analytics reset when the tab closes, because nothing is stored.
- A configured engine on another origin works for the WebSocket, but `/api/info` from the page would need CORS, which the backend does not send.
- On Windows, web's vitest must be started from an upper-case `C:\` path.

## 16. Out of scope (future iterations)

TTS/LLM input, product features beyond this UI (saved history, accounts), RTX 4050 optimisation, third-party integrations, final test-split evaluation.

## 17. Commits

On branch `iteration/lovable-ui-integration`, in order: the UI as delivered; engine connection, serving and honest content; Prettier formatting (whitespace only); browser test, visual comparison, HEAD routes and the per-second counter fix; the diagnostics base-path fix and this report; audio-file input with MP4 export.
