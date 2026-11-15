# Architecture hypotheses

What Keyframe publicly says about its architecture, what we infer, what stays unknown, and which principles EmoStream adopts. Labels are defined in [evidence_and_limitations.md](evidence_and_limitations.md). Nothing here claims to recover Keyframe's implementation.

## 1. Publicly described architecture (persona-1.5-live)

Source: the research article "Semantic Codes: Decoupling Behavior from Appearance in Real-Time Avatars", 27 March 2026 (E5). All rows **[DOC]**.

```
raw audio ─┐
emotion  ──┼─► behaviour model ──► semantic codes ──► diffusion renderer ──► frames (25 FPS)
prev codes ┘   (chunked AR,         (per frame)        (+ persona appearance,
               diffusion over                           few-step, no history)
               code windows)
```

| Component | Stated | Not stated |
|---|---|---|
| Factorisation | Behaviour and appearance are modelled separately because appearance is nearly constant in a conversation and behaviour changes every frame. The code space is a stable interface: the renderer can be replaced without retraining the behaviour model. | — |
| Semantic codes | Learned "from conversational video"; "no landmark detector, blendshape basis, or 3D prior in the loop"; after training they separate pose, gaze and expression from identity, lighting and background. | Dimensionality, rate, continuous vs. quantised, encoder, training objective |
| Behaviour model | "Chunked-autoregressive"; conditional diffusion over code sequences; a transformer denoises windows of future codes; conditioned on raw audio, an emotion target and already-produced codes; trained to continue an existing sequence; loss penalises motion errors rather than per-frame errors; "single-digit milliseconds" per window; "a handful of denoising steps". | Parameter count, window length, context length, look-ahead, audio encoder |
| Guidance | Audio, emotion and motion prefix are each dropped independently in training to a learned null embedding; at inference each has its own classifier-free guidance scale, combined leave-one-out in one batched forward pass; scales are tuned by a preference-optimisation pass before release. | Scale values |
| Emotion | "Discrete emotion targets" supplied per window; intensity follows the emotion guidance scale; continuous emotion is future work. | Emotion list (the SDK lists 11) |
| Renderer | Diffusion, "amortized" (each frame rendered fresh from codes + appearance, no history), distilled to "a few steps"; dominant per-frame cost. | Backbone, resolution, how appearance is encoded |
| Performance | ~180 ms audio-to-video; ~500 ms turn; faster than real time on one GPU; hundreds of conversations per deployment; $0.06/min. | GPU type, VRAM, batch size |
| Limits acknowledged | One side of the dialogue only (no listening behaviour), discrete emotion, no minute-scale memory. | — |

## 2. Hypotheses (ours)

| # | Hypothesis | Basis | Confidence |
|---|---|---|---|
| H1 | The "200M parameter" figure describes mainly the renderer; the behaviour model is far smaller. | The article says code generation is "thousands of times smaller than generating pixels" and runs in single-digit ms. [INF] | Medium |
| H2 | The behaviour window is on the order of a few hundred milliseconds to one second of codes. | 180 ms model latency plus the SDK remark that the final partial *second* renders only after end-of-turn. [INF] | Low–medium |
| H3 | Some audio look-ahead is used, which is part of the ~180 ms. | "the leading audio the first chunk needs" (E5). [INF] | Medium |
| H4 | The GPU worker is a Python LiveKit participant that batches many sessions on one GPU. | `windy_serve/audio/framing.py` path in the SDK comment (STATIC, E4); "one GPU serving many conversations" (DOC, E5). [INF] | Medium |
| H5 | persona-2.0-live's "word-level control" is the timed-cue protocol: emotion cues at sample offsets, applied per 40 ms frame. | SDK 0.3.0 framing (STATIC, E4) and changelog wording (DOC, E7). Whether the model itself changed is unknown. [INF] | Medium |
| H6 | Image-to-avatar needs more than one forward pass (enrolment or fine-tuning). | It is Enterprise-only and absent from the public API. [INF] | Low |

## 3. Why we do not copy the architecture

- The codes, both models and their training data are unpublished, and training a diffusion renderer plus a learned code space from conversational video is far outside one academic year and a 6 GB target GPU.
- Diffusion sampling for the behaviour model costs several network evaluations per window; whether that is needed at our scale is an empirical question (Phase 6 starts from the simplest model that works).

## 4. Principles EmoStream adopts

| Principle (from the reference) | EmoStream realisation | Status |
|---|---|---|
| Separate identity/appearance from behaviour | A frozen pretrained portrait renderer encodes the portrait once; a separate small model predicts motion | Design decision; renderer selected in Phase 3/5 |
| Predict motion, not pixels | The behaviour model outputs a compact per-frame motion vector the renderer already understands (implicit-keypoint expression deltas and head pose), not images | Depends on the renderer chosen |
| A stable motion interface | The motion vector format is fixed by the renderer, so the behaviour model and renderer can be developed and benchmarked independently | Design decision |
| Chunked streaming with previous motion as context | Carry model state and the last emitted motion across audio chunks; train with the same chunking used at inference | To be validated by chunked-vs-full-sequence equivalence tests |
| Raw audio conditioning | Self-supervised speech features (HuBERT/WavLM) from raw 16 kHz audio | Ablation planned |
| Explicit, independent emotion conditioning | Emotion label + intensity as separate inputs with their own branch, fused region-aware so the mouth is protected | Phase 6 |
| Motion-space loss for smoothness | Velocity/acceleration terms in the training loss; boundary-jerk metric in evaluation | Phase 6/8 |
| Idle behaviour instead of freezing | Blink/gaze/pose generation that continues during silence | Phase 6 |

## 5. Differences we accept

| Aspect | Keyframe (stated) | EmoStream |
|---|---|---|
| Motion representation | Learned codes, no rig or landmarks | The pretrained renderer's own motion space (not learned by us) |
| Renderer | Diffusion, distilled | Warping + decoder (feed-forward, one pass per frame) |
| Identity | Stock or enterprise-enrolled personas | One-shot from a single image |
| Scale | Hundreds of sessions per GPU | One session |
| Emotions | 11 discrete labels, no public intensity | 5 labels with intensity 0–1 |

The trade is deliberate: a feed-forward warping renderer cannot match a diffusion renderer's photorealism on large head rotations, but it is one-shot, runs in real time on a single mid-range GPU, and has public weights.
