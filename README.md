# EmoStream

**One static portrait + voice → a talking, emotion-controllable avatar.**

EmoStream animates a single photo with speech from a microphone or an audio file. It keeps the person's identity, moves lips, jaw, brows and head, blinks, and lets the user pick an emotion (neutral, happy, sad, angry, surprised) and its intensity (0–1) while speaking.

This is the second implementation of the FYP project described in [`docs/reference/FYP_Mid_Report.pdf`](docs/reference/FYP_Mid_Report.pdf), started from scratch in November 2026. Nothing from the first implementation is reused.

## How it works

```
portrait ──► face crop ──► appearance volume (once)
                                   │
audio ──► streaming HuBERT ──► behaviour model ──► motion (69 numbers / frame) ──► warp + decode ──► frame
              emotion, intensity ───┘                                                (LivePortrait, frozen)
```

- **Renderer:** LivePortrait, frozen, as packaged in [Ditto](https://github.com/antgroup/ditto-talkinghead) (Apache-2.0).
- **Behaviour model:** two interchangeable options.
  - `emostream` — ours. A 1.36 M-parameter causal network with an articulation branch and an emotion branch, trained on MEAD with an amplitude-preserving loss. Algorithmic delay 200 ms with per-frame streaming.
  - `ditto` — Ditto's pretrained motion-diffusion model, used as the baseline. Algorithmic delay 520–880 ms.
- **Engine:** sample-accurate chunking, per-frame emotion timeline, tail flush, per-stage timing, latency tracking, visible "AI-generated" watermark, consent gate.

Details: [`docs/architecture/emostream_architecture.md`](docs/architecture/emostream_architecture.md). Why this stack: [`docs/architecture/model_selection.md`](docs/architecture/model_selection.md).

## Status

Two rounds of work so far. Numbers are on **validation actors** (unseen in training); the six test actors have not been touched.

**Current iteration (animation quality, 16 Nov 2026)** — full report: [`docs/iterations/current_iteration/final_iteration_report.md`](docs/iterations/current_iteration/final_iteration_report.md)

| Measure | Previous (`reg`) | Now (`it_ccc_la2`) | Real video |
|---|---|---|---|
| Mouth opening, share of real movement | 0.40 | 0.72–0.78 | 1.0 |
| Jaw movement, share of real | 0.50 | 0.78–0.87 | 1.0 |
| Upper-face movement, share of real | 0.39 | 0.84 | 1.0 |
| Emotion macro-F1 (target ≥ 0.70) | 0.65 | 0.75–0.81 | 0.73 |
| ArcFace identity (target ≥ 0.80) | 0.93 | 0.88–0.92 | 0.75 |
| SyncNet LSE-C | 4.79 | 4.76 (not improved) | 5.78 |
| Server latency p50 / p95, L40S (targets 350 / 500 ms) | 269 / 319 ms | 270 / 273 ms | — |
| Frames drawn in the browser | ~10.5 per second, in bursts | 23.9 per second, evenly paced | — |

Not yet done: a browser test by a person with a real microphone, human ratings, the test split, the RTX 4050.

| Area | Record |
|---|---|
| Reference-product study (Keyframe Labs) | [`docs/reverse_engineering/`](docs/reverse_engineering/) |
| Pretrained candidates on the same inputs | [`2026-11-14_pretrained_poc.md`](docs/experiments/2026-11-14_pretrained_poc.md) |
| MEAD validation, manifest, splits | [`2026-11-14_mead_validation.md`](docs/experiments/2026-11-14_mead_validation.md) |
| Engine and renderer speed | [`2026-11-14_engine_and_renderer.md`](docs/experiments/2026-11-14_engine_and_renderer.md) |
| First behaviour model and its evaluation | [`2026-11-15_behaviour_model_training.md`](docs/experiments/2026-11-15_behaviour_model_training.md), [`2026-11-15_validation_report.md`](docs/evaluation/2026-11-15_validation_report.md) |
| Animation-quality iteration | [`docs/iterations/current_iteration/`](docs/iterations/current_iteration/) |
| Frontend ↔ backend contract | [`docs/integration/frontend_backend_contract.md`](docs/integration/frontend_backend_contract.md) |

## Repository layout

```
emostream/            engine, behaviour model, training code, metrics, safety
  audio/clock.py        sample-accurate clock and streaming windows
  engine/               runtime (renderer), behaviours, emotion timeline, session
  models/               BehaviourNet
  training/             data pipeline and trainer
  metrics/              motion smoothness and boundary jerk
backend/              FastAPI app: /ws/session (live), /api/export (MP4), /api/info
frontend/             React + TypeScript + Vite client
modal/apps/           Modal jobs: PoC runs, MEAD jobs, training, evaluation, benchmarks, serving
tests/                pytest (CPU only)
docs/                 reference, reverse engineering, architecture, experiments, evaluation
```

## Run it

Requirements: Python 3.10+, Node 18+, the Modal CLI (authenticated), and access to the Modal volumes named in `CLAUDE.md`.

```bash
# tests (no GPU needed)
python -m pytest tests -q
cd frontend && npm install && npm test && npm run build && cd ..

# live app on a Modal GPU (prints a URL; the worker stops after 5 idle minutes).
# Defaults: L40S + TensorRT. Cheaper: EMOSTREAM_GPU=A10G. Stop it with: modal app stop emostream-v2-live
modal deploy modal/apps/serve.py

# offline: one portrait + one audio file through the engine, with timing
modal run modal/apps/live_bench.py --behaviour emostream --run it_ccc_la2 --tensorrt --hop 1 --emotion-gain 1.5 --gpu L40S
```

Reproducing the experiments, in order:

```bash
modal run modal/apps/mead_survey.py              # read-only survey of the raw data
modal run modal/apps/mead_manifest.py            # level 2/3 extraction, validation, splits
modal run modal/apps/mead_preprocess.py          # motion targets + speech features (GPU, ~7 GPU-hours)
modal run modal/apps/train_behaviour.py --run it_ccc_la2 --steps 5000 --dropout 0.3 --weight-decay 0.01 --w-ccc 1.0 --lookahead 2
modal run modal/apps/evaluate.py::gen --behaviour emostream --run it_ccc_la2 --tag val_it_ccc_la2_h5
```

GPU jobs cost money. Preprocessing is the expensive one; training a model takes a few minutes on a T4.

## Using the live app

1. Choose a photo of one face looking at the camera.
2. Confirm that the person in the photo and the speaker have agreed.
3. Pick microphone or an audio file, then start.
4. Change emotion and intensity at any time.
5. Stop. The session can be saved as a video; an uploaded recording can also be rendered to MP4.

The wire protocol is documented at the top of [`backend/streaming/protocol.py`](backend/streaming/protocol.py).

## Safety

- A session cannot start without consent for both the portrait and the voice (enforced in the engine, the API and the client).
- Every output frame carries a visible "AI-generated" label; it is applied inside the engine and cannot be switched off from the API.
- Uploaded portraits and audio are held in memory or in a temporary file for the duration of a request and then deleted. Nothing is logged or stored.
- No voice cloning, speech synthesis or identity search. Do not use the system to impersonate anyone.

## Licences of what this builds on

| Component | Licence | Note |
|---|---|---|
| Ditto (code, motion model, packaged LivePortrait weights) | Apache-2.0 | Pinned at commit `c3e47ee` |
| LivePortrait | MIT | |
| Face detector / landmark models bundled with Ditto | InsightFace model terms | Non-commercial research use |
| MEAD dataset | Research use, per its authors | Stays on the private Modal volume; never committed |
| SyncNet, Wav2Lip scoring scripts, HSEmotion, InsightFace (evaluation only) | Their own licences | Wav2Lip is non-commercial |

The project is academic. A commercial deployment would need the face-analysis models replaced and the dataset terms reviewed.

## Known limitations

- Visual quality is capped by the frozen renderer: large head turns and anything outside the face crop are not handled well.
- Mouth and jaw now move at 72–87 % of a real speaker's amplitude, but articulation timing is only moderately accurate (correlation 0.55–0.58 with real video), and blinks and gaze are scripted rather than learned.
- A portrait's own expression becomes the avatar's resting face. An open mouth is closed automatically; a smile with closed lips is not removed. Use a relaxed, closed-mouth photo.
- 25 FPS was measured on an L40S; an A10G reaches about 23 FPS and keeps latency bounded by skipping frames. The project's reference laptop GPU (RTX 4050, 6 GB) was not available for testing.
- Neutral speech is often read as "happy" by the emotion classifier, and intensity values between 0 and 1 have not been scored.
- One live session per GPU worker.
