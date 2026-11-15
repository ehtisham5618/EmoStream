# Product observation — Keyframe Labs

Labels and evidence IDs (E1–E7) are defined in [evidence_and_limitations.md](evidence_and_limitations.md).

## What the product is

- **[DOC, E2]** Positioning: "We build human foundation models"; "Bring AI to life with lifelike, interactive avatars"; "photoreal, conversational humans".
- **[DOC, E2/E6]** The product is a *visual layer for voice agents*: the customer brings an LLM and a voice model (logos shown: OpenAI, Cartesia, Grok, ElevenLabs, Gemini, Fish, Qwen, Sonnet, Hume, Rime), streams the agent's speech audio to Keyframe, and receives avatar video.
- **[DOC, E2]** Four headline capabilities: Human realism, Ultra-low latency, Emotion control, Image-to-avatar.
- **[DOC, E2]** Headline numbers on the homepage: "Ultra-low latency, 1000s of concurrency, 5-min setup, Unlimited call length", "As low as $0.06/min".

## Models

| Model | Status | Public statements | Source |
|---|---|---|---|
| `persona-1-live` | Retired | Docs: "Do not reference persona-1-live; it is retired." | [DOC, E6] |
| `persona-1.5-live` | GA 14 Apr 2026 | "200M parameter model"; first model with emotion (docs: anger, happiness, sadness); ~180 ms audio-in to video-out; ~500 ms typical turn | [DOC, E2/E5/E7] |
| `persona-2.0-live` | Preview 12 Oct 2026, GA 12 Nov 2026 | "Precise, word-level control over expression" | [DOC, E2/E7] |

## Homepage structure (observed)

- **[OBS, E2]** Next.js application built with Turbopack and served with a Vercel deployment id (`?dpl=dpl_…` on every chunk URL). 16 scripts, 6 fonts, 3 stylesheets, all same-origin.
- **[OBS, E2]** The DOM contains 6 `<video>` elements with 5 `<source>` children, 13 `<canvas>` elements, 27 buttons, no `<iframe>`, no `<form>`. So the showcase clips are pre-recorded video files, not live inference.
- **[OBS, E2]** A live-demo widget is present with controls labelled "Change avatar: Cosmo", "Start call", "Unmute preview". It was not activated (see limitations).
- **[OBS, E2]** No network requests and no WebSocket connections occurred during the 4 s passive window on the idle page, and no web workers were present.
- **[OBS, E2]** The page shows an SDK snippet: `createClient({ onVideoTrack, onAudioTrack })`, `await avatarSession.connect()`, `avatarSession.sendAudio(pcmAudioBytes)`.

## User-visible interaction sequence

Not observed live. From docs and SDK:

1. **[DOC, E6]** The customer's server calls `POST https://api.keyframelabs.com/v1/sessions` with a persona (stock avatar) or agent id and gets `server_url`, `participant_token`, `agent_identity`.
2. **[STATIC, E4]** The browser SDK joins a LiveKit room with that token and subscribes to the avatar participant's video and audio tracks.
3. **[STATIC, E4]** The client streams 24 kHz 16-bit mono PCM speech to the avatar; the avatar publishes video plus the same audio, synchronised.
4. **[STATIC, E4]** The avatar worker signals `speaking` / `listening` state changes by RPC; the client can `interrupt()` and `setEmotion()`.
5. **[DOC, E5]** With no audio the avatar shows idle behaviour (blinks, small gaze and posture shifts) rather than freezing.

## Image-to-avatar

- **[DOC, E2]** Advertised as a core capability ("04 Image-to-avatar", "CUSTOM / IMAGE-TO-AVATAR", an "IMAGE.PNG" illustration).
- **[DOC, E7]** On the pricing page it is listed only under the Enterprise plan.
- **[UNK]** Input requirements, enrolment time, whether enrolment involves per-identity fine-tuning or is feed-forward, and what the public API for it looks like. The public OpenAPI file has no persona-creation endpoint (E6).

## Commercial envelope

- **[DOC, E7]** Plans: Free (30 min, 5-minute conversation limit, 1 concurrent session), Starter $50, Growth $100, Scale $300, Enterprise. Both live models cost 6 credits per minute.
- **[DOC, E7]** Self-run human benchmark "EmoteBench" (250 participants, 19,500 judgments, late October 2026): muted-clip emotion recognition 81% for persona-2.0-live versus 32–37% for three competitors; chance is 14% (seven emotions). The page states Keyframe designed and ran the study and that code and data are "coming soon", so this is an unverified vendor result.

## What this means for EmoStream

The observable product is *audio in → synchronised avatar video out, with a discrete emotion switch*. It is not a chatbot: the LLM and TTS are the customer's. That matches EmoStream's scope (portrait + voice → animated avatar) and confirms that microphone/audio-driven animation with an emotion control is the core to build, with everything conversational out of scope.
