# Iteration report: animation quality

Branch `iteration/animation-quality`, 15–16 November 2026. Baseline: commit `f16802c`, checkpoint `reg`.

## Outcome

The avatar now opens its mouth and moves its jaw about twice as much as before, moves its brows, cheeks and head, shows clearer emotions, rests with a closed mouth even when the photo's mouth is open, and is presented in the browser as an even 24–25 frames per second instead of bursts. Lip-sync timing improved only slightly and the SyncNet score did not change. No human ratings were collected, and the browser test used a recording played through a fake microphone, not a person at a microphone.

**The first iteration is not complete.** By the agreed conditions it still needs: your own browser test with a real microphone, your approval of the animation quality, and the Lovable UI and its integration.

## Results on validation actors (unseen in training)

| Measure | Before (`reg`) | Now (`it_ccc_la2`) | Real video | Target | Met? |
|---|---|---|---|---|---|
| Mouth opening, share of real movement | 0.40 | 0.72–0.78 | 1.0 | — | improved |
| Jaw movement, share of real | 0.50 | 0.78–0.87 | 1.0 | — | improved |
| Mouth-opening timing (correlation with real) | 0.52 | 0.55–0.58 | — (renderer limit 0.94) | — | slightly improved |
| Upper-face movement, share of real | 0.39 | 0.84 | 1.0 | — | improved |
| Head rotation variation, share of real | 0.25–0.40 | about 0.80 | 1.0 | — | improved |
| Emotion macro-F1 | 0.651 | 0.754; 0.811 at strength 1.5 | 0.734 | ≥ 0.70 | **yes** |
| Emotion gain over Ditto baseline | +44 pts | +54 to +60 pts | — | ≥ +10 pts | yes |
| ArcFace identity | 0.930 | 0.916; 0.883 at strength 1.5 | 0.754 | ≥ 0.80 | yes |
| SyncNet LSE-C / LSE-D | 4.79 / 9.18 | 4.76 / 9.56 | 5.78 / 8.69 | within 5 % of baseline (LSE-C) | yes for LSE-C; **not improved** |
| Server latency p50 / p95 (L40S) | 269 / 319 ms | 270 / 273 ms | — | ≤ 350 / ≤ 500 ms | yes |
| Frame rate (L40S, five minutes) | 25.0, none skipped | 25.0, none skipped | — | 25 FPS | yes on L40S |
| Peak GPU memory | 2.77 GiB | 2.77 GiB | — | ≤ 6 GB | yes on tested GPUs |
| Five-minute stability | 7,500 / 7,500 | 7,500 / 7,500 | — | no drift | yes (engine side) |
| Boundary jerk at emotion changes | −84 % | not re-measured | — | −20 % | previously met |
| Frames drawn in the browser | about 10.5 per second, in bursts | 23.9 per second; 76 % of intervals at 30–50 ms | — | continuous | improved; see limits |
| Voice-to-face delay in the browser | 1.0–1.6 s (recordings); 2.6 s reproduced | 0.55 s (Pakistan → US-East) | — | — | improved |

Ranges are across streaming mode and emotion strength; the live default is `it_ccc_la2`, per-frame streaming, emotion strength 1.5. Conditions and sample sizes are in the linked documents.

## What was already working

Identity preservation; explicit emotion control far above the Ditto baseline; exact neutrality at intensity 0; chunk-invariant streaming; 25 FPS and sub-350 ms server latency on an L40S; smooth emotion transitions; consent gate and watermark.

## What was improved

| Area | Change | Document |
|---|---|---|
| Mouth and jaw amplitude | Concordance-correlation loss; two frames of look-ahead | `articulation_improvement.md` |
| Upper face and head | Same loss; both now move at about 80 % of real | `facial_motion_evaluation.md` |
| Emotion recognisability | Fuller expression from the new loss; emotion branch scaled 1.5 by default | `emotion_control_evaluation.md` |
| Neutral | "Happy" misreadings 11 → 5 of 16, level with real video | same |
| Open-mouthed portraits | Lips closed automatically before animating; the user is told | `browser_session_quality_analysis.md` |
| Browser stutter | Paced player with a bounded buffer and explicit late-frame policy | `browser_playback_diagnostics.md` |
| Browser lag | Start-up audio backlog removed; 80 ms microphone chunks; per-frame streaming | same |
| Telemetry | On-screen and downloadable client diagnostics; external draw-time measurement | same |
| Integration contract | Written from the implemented backend | `docs/integration/frontend_backend_contract.md` |

## What was not improved

- **Lip-sync timing.** Mouth correlation rose from 0.52 to at most 0.58; SyncNet is unchanged. The mouth moves more, at about the same accuracy as before.
- **Phoneme-level articulation** (bilabial closure, rounding): not measured, so no claim.
- **Blinks and gaze:** unchanged — scheduled blinks, eyes fixed on the camera.
- **Head-motion timing:** liveliness improved; whether nods fall at the right moments was not evaluated.
- **Emotion strength:** still below real acted level-3 expressions (29–47 % as trained, roughly 45–70 % at strength 1.5).
- **Neutral selected with an emotional voice:** about a quarter of the voice's emotion leaks into the face.

## What remains limited by the renderer

- Only the 512 px face crop moves; shoulders and hair outside it are static.
- A portrait's own expression becomes the rest pose. Open mouths are corrected; closed-lip smiles and raised brows are not.
- Large head turns are untested (MEAD front view contains only small rotations).
- 21 keypoints limit fine brow and eyelid detail.

For mouth, jaw and expression strength the renderer is **not** the limit: driven by real motion it reproduces 94 % of real mouth opening and the same emotion score as real video.

## What was tested

- 62 Python tests and 10 frontend tests pass (new: streaming with look-ahead and both hops, the loss, the playout clock including backlog and lateness).
- Rendered-video scoring on 80 validation clips for nine configurations; SyncNet on three.
- Motion-space analyses on 1,589 validation clips and on all 25 voice × selection combinations.
- Renderer oracle; ground-truth audio-video offset check.
- Live engine: 60 s on A10G and L40S in three configurations; 300 s on L40S.
- Real browser (headless Chromium, fake microphone) against a local timing stand-in and against the deployed L40S worker.

## What was not tested

- **The six held-out test actors** — untouched, by design.
- A person speaking into a real microphone on a visible display.
- A five-minute session in the browser (five minutes was engine-side only).
- Human ratings of naturalness or emotion.
- Rendered intensity sweep; cross-conditioning at strength 1.5; boundary jerk for the new checkpoint.
- Audio-video offset for uploaded files in the browser.
- The RTX 4050 (a later iteration).

## Acceptance criteria

| Criterion | Status |
|---|---|
| Accurate and natural speech articulation | Amplitude much improved; timing accuracy modest; naturalness not rated by people |
| Correct jaw and mouth movement | Improved to 72–87 % of real movement |
| Recognisable selected emotions | Yes by classifier (0.75–0.81), including against a mismatched voice for four of five |
| Intensity behaves continuously | Yes in motion space; not checked on rendered video |
| Full-face motion | Yes: upper face 84 % of real |
| Natural head, eye and eyebrow movement | Head and brows improved; eyes unchanged |
| No obvious repetitive motion | Blink intervals are random; nothing periodic seen; not formally tested |
| No visible facial jitter | None seen in frame sheets; not measured |
| No noticeable browser stuttering | 76 % of intervals at 30–50 ms, 1.7 % over 80 ms, one 533 ms gap in 45 s |
| Stable audio-video synchronisation | Server timeline is sample-accurate; browser offset for uploads instrumented, not measured |
| Preserved identity | Yes (0.88–0.92) |
| Smooth five-minute sessions | Yes engine-side; not in the browser |

## What to run

The improved system is deployed in the `abdulmat40` workspace and scales to zero when idle:

`https://abdulmat40--emostream-v2-live-web.us-east.modal.run`

The first request after a pause waits for a cold start (model loading). An L40S costs about $2 per hour while a session is open and for five minutes afterwards. To stop it entirely: `MODAL_PROFILE=abdulmat40 modal app stop emostream-v2-live`.

For your test, open "Playback diagnostics" on the page and use "Save diagnostics file" at the end; that file answers which part of any remaining delay is network, server or browser. Side-by-side comparison videos (real | previous | improved) are in `outputs/compare/side_by_side/` on this PC.

To run the previous baseline for comparison: `EMOSTREAM_RUN=reg EMOSTREAM_EMOTION_GAIN=1.0 EMOSTREAM_HOP=5`.

## Recommended next steps within this iteration

1. Your browser test with a real microphone and a neutral, closed-mouth photo, with the diagnostics file.
2. If articulation timing is still the weak point: recompute speech features per frame and retrain (removes the per-frame streaming penalty), then consider a model that predicts a distribution rather than an average.
3. A small human rating of the side-by-side clips.
4. Deploy a worker in a region closer to the user to remove about 300 ms of network delay.
