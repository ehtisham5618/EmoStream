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
  - `emostream` — ours. A 1.36 M-parameter causal network with an articulation branch and an emotion branch, trained on MEAD. Algorithmic delay 120–280 ms.
  - `ditto` — Ditto's pretrained motion-diffusion model, used as the baseline. Algorithmic delay 520–880 ms.
- **Engine:** sample-accurate chunking, per-frame emotion timeline, tail flush, per-stage timing, latency tracking, visible "AI-generated" watermark, consent gate.

Details: [`docs/architecture/emostream_architecture.md`](docs/architecture/emostream_architecture.md). Why this stack: [`docs/architecture/model_selection.md`](docs/architecture/model_selection.md).

## Status

Measured on **validation actors** (unseen in training); the test split has not been touched. Full conditions are in the linked records.

| Target | Result | Met? |
|---|---|---|
| 25 FPS at ≥ 256×256 | 25.0 FPS at 512×512 for five minutes, no skipped frames (L40S, TensorRT) | Yes on L40S; 23 FPS on A10G; RTX 4050 not tested |
| Latency p50 ≤ 350 ms, p95 ≤ 500 ms | 269 ms / 319 ms on the server | Yes (network time is extra) |
| Peak GPU memory ≤ 6 GB | 2.8 GiB | Yes on the GPUs tested |
| Five-minute stability | 7,500 / 7,500 frames, no drift | Yes |
| Emotion macro-F1 ≥ 0.70 | 0.65 (Ditto baseline 0.21; real video 0.73) | No, 5 points short |
| ArcFace identity ≥ 0.80 | 0.93 | Yes |
| Lip sync within 5 % of the baseline | LSE-C 4.79 vs 4.75 (real video 5.78) | Yes |
| Boundary jerk −20 % at emotion changes | −84 % | Yes |

| Area | State | Record |
|---|---|---|
| Reference-product study (Keyframe Labs) | Public pages, docs and SDK; no live session observed | [`docs/reverse_engineering/`](docs/reverse_engineering/) |
| Pretrained candidates on the same inputs | SadTalker, Ditto, AniPortrait, Hallo2 all run | [`2026-11-14_pretrained_poc.md`](docs/experiments/2026-11-14_pretrained_poc.md) |
| MEAD validation, manifest, splits | 16,988 valid clips, 33 / 4 / 6 actors | [`2026-11-14_mead_validation.md`](docs/experiments/2026-11-14_mead_validation.md) |
| Engine and renderer speed | PyTorch vs TensorRT, per-stage times | [`2026-11-14_engine_and_renderer.md`](docs/experiments/2026-11-14_engine_and_renderer.md) |
| Behaviour model training | Four runs; `reg` selected on validation | [`2026-11-15_behaviour_model_training.md`](docs/experiments/2026-11-15_behaviour_model_training.md) |
| Evaluation | Lip sync, emotion, identity, real time, transitions, deployed app | [`2026-11-15_validation_report.md`](docs/evaluation/2026-11-15_validation_report.md) |
| Live application | Deployed and driven end to end by a WebSocket client; not yet tried in a browser with a real microphone | `backend/`, `frontend/`, `modal/apps/serve.py` |

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
modal run modal/apps/live_bench.py --behaviour emostream --run reg --gpu A10G
```

Reproducing the experiments, in order:

```bash
modal run modal/apps/mead_survey.py              # read-only survey of the raw data
modal run modal/apps/mead_manifest.py            # level 2/3 extraction, validation, splits
modal run modal/apps/mead_preprocess.py          # motion targets + speech features (GPU, ~7 GPU-hours)
modal run modal/apps/train_behaviour.py --run reg --steps 5000 --dropout 0.3 --weight-decay 0.01
modal run modal/apps/evaluate.py::gen --behaviour emostream --run reg --tag val_emostream_reg
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
- Our behaviour model regresses motion, so the mouth is less lively than a real speaker's and head motion is calm.
- 25 FPS was measured on an L40S; an A10G reaches about 23 FPS and keeps latency bounded by skipping frames. The project's reference laptop GPU (RTX 4050, 6 GB) was not available for testing.
- Neutral speech is often read as "happy" by the emotion classifier, and intensity values between 0 and 1 have not been scored.
- One live session per GPU worker.
