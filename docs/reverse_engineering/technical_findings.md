# Technical findings — Keyframe Labs

Labels and evidence IDs are defined in [evidence_and_limitations.md](evidence_and_limitations.md).

## 1. Web application

| Finding | Label |
|---|---|
| Marketing site is a Next.js app bundled with Turbopack (`/_next/static/chunks/turbopack-*.js`) on Vercel (`?dpl=dpl_…` deployment id on every chunk). | OBS (E2) |
| 16 scripts captured; 15 parsed (229,345 AST nodes), 1 timed out. No API endpoint candidates were found in the parsed scripts. No source maps declared. | STATIC (E3) |
| Idle homepage opens no WebSocket and makes no requests in the observation window; demo videos are `<video>` files. | OBS (E2) |
| The live demo's session-creation call is not visible in static analysis of the parsed chunks. It is either in the timed-out chunk, loaded on demand, or made through a server action. | INF / UNK |

## 2. Public HTTP API (documented, not called)

All **[DOC, E6]**.

- Base: `https://api.keyframelabs.com/v1`, bearer API key, server-side only.
- `POST /sessions` — body is exactly one of `persona_id`, `persona_slug` (e.g. `public:cosmo_persona-1.5-live`) or `agent_id`. Response: `server_url` (example `wss://rtc.keyframelabs.com`), `participant_token` (JWT), `agent_identity`, `voice_agent_details`.
- Errors include `503` for no capacity, `403` when a model is not allowed on the plan.
- Other resources: `/agents`, `/avatars`, `/voices`, `/llm-models`, `/uploads`, `/generations` (batch renders: mp4/webm/mov; audio uploads accepted, files with a video stream rejected), `/meet-bot`.
- No public endpoint creates a persona from an image.

## 3. Client SDK and wire protocol

All **[STATIC, E4]** from `@keyframelabs/sdk` 0.3.0 (`dist/PersonaSession.js`, `framing.js`, `audio-utils.js`, `types.d.ts`).

**Transport.** The SDK's only runtime dependency is `livekit-client`. `connect()` creates a LiveKit `Room` and joins with `serverUrl` + `participantToken`. The option docs call these the "WebRTC URL" and "WebRTC access token". The avatar is a remote participant identified by `agentIdentity`; its video and audio arrive as subscribed `MediaStreamTrack`s.

**Audio upload.** Not a microphone track. Audio is written to a LiveKit *byte stream* on topic `lk.audio_stream`, addressed to the avatar participant:

- Format: PCM16 little-endian, 24,000 Hz, mono (`SAMPLE_RATE = 24000`, `BYTES_PER_SAMPLE = 2`, `CHANNELS = 1`).
- The stream opens on the first write and is closed by `endAudioTurn()`. The SDK comment says the avatar "renders the final partial second only after it" — i.e. the worker buffers a sub-second tail until the turn ends.
- Writes are serialised through a promise queue to preserve order.

**Framed stream (protocol ≥ 2).** If the avatar participant advertises attribute `kfl.protocol >= 2`, the stream is opened with attribute `kfl.framing: "1"` and carries records `type (u8) | length (u32 LE) | payload`:

- `0x01` audio: PCM16LE 24 kHz mono.
- `0x02` cue: UTF-8 JSON `{"emotion": "<name>", "at": <sample offset from stream start>}`.

The source comment names the server counterpart: "Must match `windy_serve/audio/framing.py` on the GPU node". So the GPU worker is a Python service.

**Control channel.** Unreliable data messages on topic `lk.control`: the literal `interrupt`, and `emotion:<name>` for untimed emotion changes. `interrupt()` is documented as clearing "pending frames in the GPU node's publish queue".

**Worker → client RPC.** `lk.playback_started` and `lk.playback_finished`; the latter carries `{"playback_position": seconds, "interrupted": bool}`.

**Emotions.** `EMOTIONS = neutral, happy, sad, angry, surprised, concerned, confused, disgusted, excited, scared, skeptical` (11). The changelog says 0.3.0 raised this from 4. A cue takes effect "on the video frame (40 ms) that holds the cue's audio sample" — frame-accurate, independent of how far ahead of playback the audio was sent.

**Frame period.** 40 ms, i.e. 25 FPS (SDK type comment; consistent with E5).

**Resampling.** The SDK ships a linear-interpolation `resamplePcm` helper, described in its own comment as "not high quality but sufficient for real-time".

## 4. Server-side integration

- **[DOC, E6]** Python plugin `livekit-agents[keyframe]~=1.4` exposes `keyframe.AvatarSession(persona_slug=… | persona_id=…)`, started with `avatar.start(session, room=ctx.room)`; `await avatar.set_emotion("happy")`. Env var `KEYFRAME_API_KEY`.
- **[DOC, E6]** Hosted pipelines for ElevenLabs Agents and OpenAI Realtime; meeting bots through Recall AI.
- **[INF]** The `lk.audio_stream` / `lk.playback_finished` topic names follow LiveKit's avatar-worker conventions, which suggests the GPU worker is implemented as a LiveKit avatar participant: it receives agent audio by data stream and publishes synchronised audio+video tracks.

## 5. Model-level statements

All **[DOC, E5]** unless marked; details in [architecture_hypotheses.md](architecture_hypotheses.md).

- Two models: a behaviour model producing "semantic codes" and a diffusion renderer producing pixels.
- Behaviour model: "chunked-autoregressive", conditional diffusion over code sequences with a transformer denoiser, conditioned on raw audio, a discrete emotion target and previously produced codes; "single-digit milliseconds" per window; "a handful of denoising steps".
- Classifier-free guidance with a separate scale per signal (audio, emotion, motion prefix); each signal is dropped independently in training to a learned null embedding.
- Renderer: "amortized" per-frame diffusion, distilled to a few steps, no history; "the dominant per-frame cost".
- 25 FPS; ~180 ms model latency; ~500 ms per turn including transport.
- "200M parameter model" for persona-1.5-live (**[DOC, E2/E7]**). Whether that counts the renderer, the behaviour model or both is **[UNK]**.

## 6. Unknowns that matter to us

| Unknown | Why it matters | How it could be resolved |
|---|---|---|
| Output resolution, real FPS, bitrate, codec | Sets the bar for our renderer | `chrome://webrtc-internals` during a demo call |
| First-frame and steady-state latency in practice | Our p50/p95 targets | Timestamped demo call observation |
| Chunk/window length of the behaviour model | Latency vs. quality trade-off | Not recoverable; must be chosen by our own experiments |
| Code dimensionality and learning method | Representation design | Not recoverable |
| Image-to-avatar mechanism | Whether one-shot is feasible at their quality | Not recoverable from public material |
| Audio encoder | Feature choice | Not stated; our own ablation (HuBERT vs. WavLM) |
