# Articulation iteration: final report, 17 November 2026

## What the user saw, and why

The user's browser sessions showed mouth movement that did not correspond to the words. Four causes were found and measured, in the order they were found:

| Cause | Evidence | Fix | Status |
|---|---|---|---|
| Old cached page played the live voice against a face 1.1 s behind (sessions 4–5) | diagnostics without new fields; server saw no acknowledgements | page not cached; out-of-date page refused with a reload message | deployed |
| A100 fallback GPU too slow: 16 % of frames skipped (session 6) | worker log; render 27 ms/frame | L40S only; batched WavLM; encoding parallel to compute | deployed |
| **Mouth-closing step over-closed open-mouthed portraits**: lips pressed, vowels opened to 20–25 % of a real speaker's opening | user's portrait (lip ratio 0.31) and recording; frame crops; per-class lip gaps | wide-open portraits closed to a relaxed ratio 0.15 | deployed |
| Model's articulation from speech: over-closing on /p b m/, weaker on degraded (real-microphone) audio | phoneme-level evaluation; degraded-speech evaluation | new model `ph_aug` (trained half the time on degraded audio) | deployed |

Details: `phoneme_articulation_diagnosis.md`, `bilabial_closure_experiments.md`, `articulation_model_experiments.md`, `phoneme_viseme_evaluation.md`, `audio_feature_alignment.md`.

## Before and after

On the user's own recording (6 test sentences) and portrait, rendered by the live engine:

| | As in the user's sessions (`wl_base`, old closing) | Now live (`ph_aug`, new closing) | Real speakers (MEAD) |
|---|---|---|---|
| Inner-lip gap error vs real speakers, mean over sound classes | 0.133 | 0.088 | 0 |
| Vowel opening minus /p b m/ gap | 0.022 | 0.070 | 0.131 |
| /p b m/ with fully closed lips | 100 % (lips never really open) | 73 % | 54 % |
| Chin pucker, pressed lips | visible | gone | — |

On MEAD validation speech (80 clips, rendered):

| Measure | `reg` | `it_ccc_la2` | `wl_base` | **`ph_aug` (live)** | Real |
|---|---|---|---|---|---|
| SyncNet LSE-C / LSE-D | — / — | 4.89 / 9.43 | 4.74 / 9.55 | **5.08 / 9.15** | 5.78 / 8.69 |
| Mouth opening corr | 0.52* | 0.546 | 0.582 | **0.600** | 1 |
| /p b m/ strict closure recall / precision | 0.38 / 0.67 | 0.67 / 0.66 | 0.90 / 0.64 | 0.85 / **0.72** | 1 / 1 |
| Inner-lip gap corr | 0.48 | 0.53 | 0.57 | **0.58** | 1 |
| Emotion F1 | — | 0.77 | 0.84 | 0.78 | 0.73 |
| ArcFace identity | — | 0.882 | 0.882 | 0.876 | 0.754 |

\* from the 16 Nov evaluation, block streaming.

Renderer check: driving the user's portrait with real recorded MEAD motion reproduces 1.18 × the real mouth opening (correlation 0.94); the model with MEAD speech reaches 1.08 ×. The renderer and the portrait are not the limit.

Live, deployed (L40S, headless Chromium, the user's recording as microphone, the user's portrait): first session after a cold start 1 of 688 frames skipped, 23.6 pictures per second drawn, voice and lips within 80 ms for 93 % of frames (median 8 ms), server 209 ms median.

## Demonstration videos (local, `outputs/demo/`, not committed)

| File | Content | Source |
|---|---|---|
| `1_mbp_bob_bought_my_map.mp4` | /p b m/ | user voice + portrait; left as in the sessions, right live now |
| `2_fv_five_very_fine_villas.mp4` | /f v/ | same |
| `3_ou_oh_rounding.mp4` | rounding: "Who knew the blue moon…", "Oh no, the old boat…" | same |
| `4_mixed_speech_all_sentences.mp4` | all six sentences | same |
| `5_neutral_mead_M005_neutral_L1_009.mp4` | neutral expression | MEAD validation clip: real, `wl_base`, `ph_aug` |
| `6_emotion_neutral_happy_angry.mp4` | emotion control | user voice + portrait, `ph_aug`: neutral, happy 0.8, angry 0.8 |

Renderer for all: LivePortrait via Ditto, TensorRT fp16, 512 px, full-face keypoints, per-frame WavLM features, emotion strength 1.5.

## What is still limited

- **Opening size on the user's own voice** is about half a MEAD speaker's average range. The renderer reproduces full real opening on this portrait, so this is the model's response to this voice; without a video of the user speaking it cannot be said how much is the user's own speaking style.
- **SyncNet** improved but remains below real video (5.08 vs 5.78).
- **Rounding** is still the weakest viseme class; dental and labiodental shapes (tongue, teeth) are not measured.
- **"Angry"** partly reads as worried (raised inner brows) on the user's portrait.
- **Network:** on this PC's connection, audio sometimes reaches the server up to 1.3 s late in bursts; the server now waits up to 1 s before skipping frames.
- Not done: human ratings; AV-HuBERT synchronisation metric (planned, not run); generative (non-averaging) motion model.

## Cost of this iteration

About $8 in `abdulmat40` (estimated from GPU minutes): phoneme pipeline and labels, degraded features, 5 training runs, 4 rendered evaluations, user-recording renders and analyses, live tests and deployments.
