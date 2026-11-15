# Behavioural specification derived from the reference product

This document turns the evidence about Keyframe Labs into behaviour EmoStream should reproduce *independently*. Each row cites where the behaviour comes from; labels are defined in [evidence_and_limitations.md](evidence_and_limitations.md). Rows marked **[OURS]** are EmoStream requirements from the FYP report that the reference product does not publicly offer.

## B1. Session lifecycle

| # | Behaviour | Basis |
|---|---|---|
| B1.1 | A session is created for one identity before any audio is sent. Identity setup happens once; per-frame work never re-processes the portrait. | DOC (E5: appearance changes little, behaviour changes every frame) |
| B1.2 | States: `disconnected → connecting → connected → (error)`; the avatar additionally reports `listening` / `speaking`. | STATIC (E4) |
| B1.3 | Closing a session releases the worker and discards queued audio and frames. | STATIC (E4) |
| B1.4 | Uploaded portrait and audio are not stored after the session unless the user asks to export. | [OURS]; DOC (E2 "zero data retention mode") |

## B2. Audio input

| # | Behaviour | Basis |
|---|---|---|
| B2.1 | Audio arrives as ordered chunks of mono 16-bit PCM at a fixed sample rate. Chunk size is the sender's choice; the receiver must not assume a size. | STATIC (E4) |
| B2.2 | Position in the stream is counted in samples from the start of the turn. All timing (frames, emotion cues) is derived from sample offsets, never from arrival time. | STATIC (E4: cue `at` is a sample offset; `turnPositionMs`) |
| B2.3 | Audio may arrive faster than real time (file upload, TTS). Output timing still follows sample position. | STATIC (E4: "however fast the audio arrives") |
| B2.4 | An explicit end-of-turn flushes the buffered tail so the final partial window is rendered. | STATIC (E4: `endAudioTurn`) |
| B2.5 | The model consumes raw audio; no transcript or phoneme stage. | DOC (E5) |

## B3. Video output

| # | Behaviour | Basis |
|---|---|---|
| B3.1 | Fixed 25 FPS; frame *k* covers audio samples `[k·T, (k+1)·T)` with `T` = 40 ms. | DOC (E5), STATIC (E4) |
| B3.2 | Audio and video are presented in sync: the frame shown at time *t* was generated from the audio heard at time *t*. | STATIC (E4: avatar publishes its own audio track) |
| B3.3 | Identity, texture, lighting and background do not drift over a session. | DOC (E5) |
| B3.4 | Motion is continuous across chunk boundaries: no jumps, freezes or repeated loops. | DOC (E5: continuation training, motion-space loss) |
| B3.5 | With silence, the avatar keeps blinking and making small gaze/posture movements. | DOC (E5) |
| B3.6 | Every output frame carries a visible "AI-generated" watermark. | [OURS] |

## B4. Facial behaviour

| # | Behaviour | Basis |
|---|---|---|
| B4.1 | Lips and jaw follow the speech. | DOC (E2) |
| B4.2 | Blinks, eyebrow movement, gaze shifts, head nods and tilts are generated, not looped from a template. | DOC (E5: codes separate pose, gaze, expression) |
| B4.3 | Non-speech sounds (laughter, hesitation) influence behaviour because conditioning is raw audio. | DOC (E5) |

## B5. Emotion control

| # | Behaviour | Basis |
|---|---|---|
| B5.1 | Emotion is an explicit discrete input, independent of the audio. | DOC (E5), STATIC (E4) |
| B5.2 | Emotion can change mid-stream; the change is tied to an audio position and takes effect on the frame containing it. | STATIC (E4) |
| B5.3 | Between turns an emotion change applies immediately. | STATIC (E4) |
| B5.4 | Required set: neutral, happy, sad, angry, surprised. | [OURS] (subset of the SDK's 11) |
| B5.5 | Intensity in [0, 1] scales how strongly the emotion is expressed; 0 is indistinguishable from neutral. | [OURS]; DOC (E5 describes an internal emotion guidance scale, not exposed) |
| B5.6 | Emotion must not degrade lip articulation: mouth closures for /p b m/ are kept under every emotion. | [OURS] (region-aware fusion requirement) |
| B5.7 | Transitions between emotions are smooth, with lower boundary jerk than an abrupt switch. | [OURS] (≥ 20% jerk reduction target) |

## B6. Responsiveness

| # | Behaviour | Basis |
|---|---|---|
| B6.1 | Model latency from audio received to frame emitted ≈ 180 ms; turn latency ≈ 500 ms. | DOC (E5) — vendor claim |
| B6.2 | EmoStream target: p50 ≤ 350 ms, p95 ≤ 500 ms audio-to-frame; ≥ 15 FPS gate, 25 FPS goal. | [OURS] |
| B6.3 | An interrupt discards queued frames so new audio is reflected quickly. | STATIC (E4) |
| B6.4 | The behaviour model is a negligible share of per-frame cost; the renderer dominates. | DOC (E5); also measured in the FYP mid-report for the earlier build (94–97%) |

## B7. Explicit non-goals

Conversation logic, speech recognition, text-to-speech, voice cloning, multi-person scenes and listening-state modelling are outside EmoStream's scope. The reference product also delegates LLM and voice to third parties (DOC, E6).
