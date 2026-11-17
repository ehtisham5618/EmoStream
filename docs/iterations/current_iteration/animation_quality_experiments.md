# Lip-sync experiments, 17 November 2026

Every comparison changes one thing. Validation actors only (M005, M024, W026, W035); the six test actors were never loaded. Workspace `abdulmat40`. Root-cause measurements that led here: `behaviour_model_root_cause.md`.

## A. Training losses (Ditto HuBERT features, all 13,057 training clips; T4, 5,000 steps)

| Run | Change from `it_ccc_la2` | Best lip corr (motion space) | Opening amp |
|---|---|---|---|
| `lt_base` | none (control; reproduced `it_ccc_la2` exactly) | 0.666 | 0.83 |
| `lt_vccc` | + lip velocity concordance | 0.656 | 0.94 |
| `lt_close` | + closed-mouth frame weighting | 0.657 | 0.89 |
| `lt_both` | both | 0.668 | 0.90 |

No gain. Not used.

## B. Live read-out position (current model; rendered, 80 clips, A10G)

| Slot | Mouth open corr | Jaw corr | LSE-C | Extra delay |
|---|---|---|---|---|
| 4 (live) | 0.546 | 0.563 | 4.89 | — |
| 2 | 0.570 | 0.567 | 4.77 | +80 ms |
| 0 | 0.570 | 0.563 | 4.58 | +160 ms |

Within noise on rendered video. Slot 4 kept.

## C. Speech encoder: WavLM-base-plus (layer 6, 1 s past, 80 ms future, one window per frame)

Data: 12,247 of 14,646 train/val clips with content-verified audio (see the pairing note in `behaviour_model_root_cause.md`). The control uses the same clips.

Motion space, 1,239 validation clips:

| Run | Features | Settings | Best lip corr | Opening amp | Upper face | Emotion cosine H / S / A / Su |
|---|---|---|---|---|---|---|
| `hb_ctrl` | Ditto HuBERT | as `it_ccc_la2` | 0.644 | 0.83 | 0.83 | 0.65 / 0.86 / 0.79 / 0.86 |
| `wl_base` | WavLM | as `it_ccc_la2` | **0.675** (step 500, then over-fits) | 0.92 | 0.85 | 0.60 / 0.82 / 0.82 / 0.87 |
| `wl_lr` | WavLM | lr 3e-4 | 0.663 | 0.83 | 0.81 | 0.63 / 0.90 / 0.88 / 0.86 |
| `wl_drop` | WavLM | dropout 0.5, lr 5e-4 | 0.665 | 0.86 | 0.85 | 0.72 / 0.82 / 0.84 / 0.85 |
| `wl_wd` | WavLM | dropout 0.5, lr 5e-4, wd 0.1 | 0.668 | 0.84 | 0.84 | 0.70 / 0.84 / 0.85 / 0.88 |

Rendered, the same 80 validation clips, live configuration (per-frame, emotion strength 1.5), A10G:

| Model | Mouth open corr / amp | Jaw corr / amp | Mouth width corr / amp | LSE-C / LSE-D (42 clips) | Emotion F1 | ArcFace |
|---|---|---|---|---|---|---|
| `it_ccc_la2` (previous live) | 0.546 / 0.81 | 0.563 / 0.89 | 0.528 / 1.01 | 4.89 / 9.43 | 0.77 | 0.882 |
| **`wl_base` (new live)** | **0.582** / 0.82 | **0.597** / 0.94 | **0.586** / 1.10 | 4.74 / 9.55 | 0.84 | 0.882 |
| `wl_wd` | 0.586 / 0.76 | 0.580 / 0.88 | 0.584 / 1.07 | 4.74 / 9.52 | 0.74 | 0.882 |

Paired per clip, `wl_base` minus previous (bootstrap 95 % interval):

| Measure | Mean difference | 95 % interval | Clips better |
|---|---|---|---|
| Mouth opening corr | +0.036 | [+0.007, +0.064] | 44 / 80 |
| Jaw corr | +0.034 | [+0.004, +0.063] | 47 / 80 |
| Mouth width corr | +0.058 | [+0.024, +0.093] | 55 / 80 |
| LSE-C | −0.15 | [−0.38, +0.08] | — |
| LSE-D | +0.12 | [−0.11, +0.35] | — |

Live, L40S, TensorRT, 60 s at microphone pace (`modal/apps/live_bench.py`):

| Model | Frames | Latency p50 / p95 / max | Speech + motion per frame | GPU memory (PyTorch) |
|---|---|---|---|---|
| `it_ccc_la2` | 1,500 / 1,500 | 243 / 274 / 301 ms | 6.7 ms | 0.39 GiB |
| `wl_base`'s sibling `wl_wd` (same features and network size) | 1,500 / 1,500 | 216 / 223 / 265 ms | 11.1 ms | 0.74 GiB |

Deployed `wl_base`, three browser sessions (headless Chromium, recorded speech as microphone, 30 s each, Pakistan → US-East): 3 / 3 started; first frames after 5.9, 4.2, 4.9 s; 24.9–25.1 frames per second drawn; 97–98 % of frames within 80 ms of their sound (median 7–9 ms).

**Decision:** `wl_base` is the live model. Articulation (opening, jaw and mouth shape) is measurably better on rendered video; SyncNet is unchanged within noise; latency is lower; emotion and identity are not worse.

**What this does not show:** whether people see the difference as clearly as the numbers do; per-phoneme accuracy (no phoneme alignment); behaviour on non-English speech.

## Side-by-side videos (real | previous | new, with the clip's audio)

`outputs/compare/wavlm/side_by_side/` (local, not committed): validation actor M005, clips 009 and 012 of each emotion, chosen by a fixed rule before looking. Per the mouth metric, the new model is better on all five 009 clips and worse on three of the five 012 clips (neutral, happy, angry).

## Cost

About $3.5 in `abdulmat40`: 9 training runs (T4), WavLM feature extraction for 37 actors (T4/A10G), 5 rendered evaluations with scoring (A10G/T4), 2 live benchmarks (L40S), deployments and browser tests. Estimated from GPU-minutes; the dashboard has the exact amount.
