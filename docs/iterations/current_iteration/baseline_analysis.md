# Baseline analysis

State of the system at the start of this iteration: commit `f16802c` on `master`, behaviour checkpoint `reg`.

## The preserved baseline

| | |
|---|---|
| Checkpoint | `emostream/reg/model.pt` on the `emostream-v2-models` volume |
| Frozen copy | `emostream/_frozen/reg_2026-11-15/model.pt` (plus `report.json`), written once and verified by download |
| SHA-256 | `d792adfe5d8a8ee786788d5c93f15c74692e1ba97dd5bf8b46525a9583fb7027` |
| Code | `master` branch; this iteration's work is on `iteration/animation-quality` |
| How to run it | `EMOSTREAM_RUN=reg EMOSTREAM_EMOTION_GAIN=1.0 EMOSTREAM_HOP=5 modal deploy modal/apps/serve.py` |

Nothing was overwritten. Every new checkpoint has its own folder.

## What the baseline did well

Measured on the four validation actors (unseen in training), reported on 2026-11-15:

- Identity: ArcFace 0.930 against the portrait.
- Lip-sync score equal to the pretrained Ditto baseline (SyncNet LSE-C 4.79 vs 4.75).
- Emotion clearly better than Ditto (macro-F1 0.651 vs 0.212).
- Engine: 25 FPS for five minutes on an L40S, server latency 269 / 319 ms (p50 / p95), 2.77 GiB.
- Chunked streaming identical to whole-sequence processing; intensity 0 exactly neutral.

## What was wrong, with measurements

New measurements made in this iteration on the unchanged baseline.

| Problem | Measurement on `reg` | Reference |
|---|---|---|
| Mouth opens too little | Rendered mouth-opening amplitude 0.40 of the real video (correlation 0.52) | 80 validation clips, landmark-based |
| Jaw moves too little | Jaw displacement 0.50 of real (correlation 0.56) | same |
| Mouth is narrow | Mouth-width variation 0.61 of real | same |
| Upper face nearly still | Upper-face expression amplitude 0.39 of real | 1,589 validation clips, motion space |
| Head nearly still | Rotation standard deviation 0.45° / 0.14° / 0.10° (pitch / yaw / roll) against 1.16° / 0.56° / 0.32° in real clips | same |
| Emotions under-expressed | At full intensity the expression reaches 36–46 % of the real level-3 strength | motion space, 4 actors |
| Neutral reads as happy | 11 of 16 neutral clips classified "happy" (real video: 4 of 16) | HSEmotion on rendered clips |
| Mouth never closes on some portraits | The portrait's own open mouth is used as the rest pose | reproduced with an open-mouthed portrait |
| Stutter in the browser | About 10.5 distinct frames per second, in bursts | the two recordings; reproduced |
| Lag in the browser | Mouth motion 1.0–1.6 s behind the voice | the two recordings; cause reproduced |

## Why: one cause behind several symptoms

The muted mouth, jaw, upper face and head share one cause. The model was trained with an L1 loss on motion. Where speech does not determine the motion exactly, the loss is minimised by predicting the average of the plausible motions. On validation, lip amplitude was 0.47–0.53 of real while lip correlation was 0.50–0.63: amplitude ≈ correlation is exactly what a mean-seeking regression gives. Head motion and brows are far less determined by audio than the lips, so they collapsed further.

Excluded as causes, each by a test:

| Hypothesis | Test | Result |
|---|---|---|
| MEAD audio and video are misaligned | SyncNet's offset estimate on 24 real validation clips; stream start times in the original files | 0 or −1 frame on 20 of 24 clips (range −4…0); both streams start at 0 |
| Motion targets are extracted wrongly | Render the extracted motion back through the renderer and compare with the real video | Mouth 0.94 correlation / 0.94 amplitude, jaw 0.92 / 0.96 |
| Normalisation suppresses amplitude | Read the pipeline: targets are standardised and un-standardised symmetrically; no clipping | Not a cause |
| The renderer cannot open the mouth | Same oracle test | The renderer reproduces 94 % of real mouth opening |
| The renderer discards expression coordinates | The engine's full-face path applies all 63; the oracle test confirms emotion survives (F1 0.725 vs 0.734 for real video) | Not a cause |
| Chunk boundaries | Chunked vs whole-sequence difference | < 1e-6 |
| Causal context too short | Two extra frames of look-ahead | Small gain (lip correlation +0.012 to +0.02); not the main cause |

The remaining two problems are engine and client defects rather than model errors: the rest pose taken from the portrait, and the browser's frame handling. See `browser_session_quality_analysis.md`.
