# EmoStream — working notes for Claude Code

EmoStream turns **one static portrait + voice audio** into a continuously animated, emotion-controllable talking avatar. This repository is the second implementation, started from scratch on 2026-11-14. The earlier implementation described in `docs/reference/FYP_Mid_Report.pdf` was discarded; the PDF is a requirements reference only.

## Hard rules

- **No results without measurement.** Targets in the report (25 FPS, ≤ 6 GB, p50 ≤ 350 ms, macro-F1 ≥ 0.70, ArcFace ≥ 0.80, …) are goals. Never write them as achieved unless a script in this repo produced the number, and say which GPU and which split.
- **No reuse of discarded artifacts.** On the Modal volume `emostream-mead-raw`, only `archives/` and `extracted/` are original data. `derived/`, `features/`, `issue2/`, `pilot/` and the whole `emostream-studio-data` volume belong to the old build: do not read them for training, evaluation or manifests.
- **The raw MEAD volume is read-only.** Mount it with `.read_only()`. All new data goes to `emostream-v2-data`; all model weights to `emostream-v2-models`.
- **The test split stays untouched** during model selection. Splits are actor-disjoint and fixed by `SPLIT_SEED` in `modal/apps/mead_manifest.py`. Select on `val`; report `test` once, at the end.
- **Never commit** checkpoints, datasets, generated media, HAR files or secrets (`.gitignore` enforces the common cases).
- **No Keyframe code or API** in the engine. Keyframe Labs is a product reference (`docs/reverse_engineering/`), nothing more.
- **Safety:** consent checkbox before upload, visible "AI-generated" watermark on every output frame, no voice cloning, uploads are not stored by default.
- Ask before launching GPU jobs expected to exceed roughly an hour or a few dollars; smaller runs are fine. State the estimated cost of each batch.
- Shell note: multi-line Python passed through a bash heredoc sometimes fails on quotes here; write the script to a file and run it.

## Current state (16 Nov 2026)

- Branch `iteration/animation-quality`; `master` holds the first build. Baseline checkpoint `reg` is frozen at `emostream/_frozen/reg_2026-11-15/` (do not overwrite). Current default checkpoint: `it_ccc_la2` (concordance loss, 2 frames look-ahead), emotion strength 1.5, per-frame streaming (hop 1) live, block streaming (hop 5) for exports.
- Live transport (16 Nov, after the user's failed browser sessions): H.264 over the WebSocket with ack-based pacing (`backend/streaming/video.py`), WebCodecs decoding and an adaptive jitter buffer in the client, and the avatar's voice played and recorded on the picture's timeline (`SyncedVoice`). JPEG frames remain as a fallback (`?video=jpeg` forces them). See `docs/iterations/current_iteration/transport_fix.md`. Local link emulation: `evaluation/benchmarks/throttle_proxy.py` + `fake_server.py --video`.
- Reports: `docs/iterations/current_iteration/`. Integration contract: `docs/integration/frontend_backend_contract.md` (keep it in step with `backend/`).
- The product UI will be supplied by the user from Lovable after the model is approved. Do not build or redesign the product frontend; `frontend/` is a test and diagnostics client.
- Future iterations (TTS/LLM input, dashboard modules, RTX 4050 optimisation, integrations, final test-split evaluation) are out of scope until the user starts them.

## Layout

```
docs/reference/            FYP mid-report (requirements)
docs/reverse_engineering/  Keyframe Labs findings, every claim labelled by evidence type
docs/architecture/         EmoStream design
docs/experiments/          Dated experiment records (PoC runs, MEAD validation, training)
docs/evaluation/           Metric definitions and reports
modal/apps/                Modal entry points (one file per job); _bench.py = shared timing/VRAM helpers
emostream/                 Python package: engine, models, data, metrics
backend/                   FastAPI app (api/, services/, streaming/)
frontend/                  React + TypeScript + Vite
training/                  configs and training entry points
evaluation/                benchmark and metric runners
tests/                     pytest
outputs/                   local downloads of generated media (git-ignored)
```

## Modal

- CLI 1.6.1. Two profiles: `ehtisham-malik5618` (holds raw MEAD and the test-split packs; credit exhausted on 15 Nov 2026) and `abdulmat40` (select with `MODAL_PROFILE=abdulmat40`; holds checkpoints, validation data and train/val packs under the same volume names, **not** the test packs or raw MEAD). The live app is deployed in `abdulmat40`. On Windows prefix commands with `PYTHONWARNINGS=ignore PYTHONIOENCODING=utf-8`; in Git Bash also `MSYS_NO_PATHCONV=1` for `modal volume` paths.
- `modal run modal/apps/<file>.py` — the directory is named `modal/` but has no `__init__.py`, so it does not shadow the installed package. Do not add one.
- L4 capacity is sometimes unavailable; functions list fallbacks (`gpu=["L4", "A10G", "T4"]`). Always record which GPU a number came from.
- Volumes: `emostream-mead-raw` (read-only source), `emostream-v2-data` (`/data`), `emostream-v2-models` (`/models`).

## Conventions

- Video is 25 FPS; one frame = 40 ms = 640 samples at 16 kHz. All timing is derived from sample offsets, never from wall-clock arrival.
- Emotions: `neutral, happy, sad, angry, surprised`; intensity in [0, 1].
- Experiment records state: date, commit of any third-party repo, GPU, input, command, raw numbers, and what was *not* measured.
