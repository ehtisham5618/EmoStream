# Articulation model experiments, 17 November 2026

All runs: WavLM-base-plus layer-6 features, the 12,247 clips with content-verified audio (11,008 train, 1,239 validation), 3,000 steps, evaluated every 250, otherwise the `wl_base` settings (concordance loss, 2 frames look-ahead, dropout 0.3, weight decay 0.01). One change per run. T4, about 6 minutes each. Validation actors only; test actors never loaded.

## Training data added

| Data | How | Coverage |
|---|---|---|
| Phoneme labels per frame | each distinct MEAD sentence transcribed (Whisper large-v3) from two actors; kept only where both transcripts agree; every clip force-aligned to its sentence's IPA phonemes (CTC aligner); frames labelled silence / 7 viseme classes / other | 210 of 400 sentences agreed; 6,336 clips labelled, mean phoneme confidence 0.79 (`modal/apps/phoneme_labels.py`) |
| Degraded-audio features | each clip's audio passed through a reproducible "real microphone" degradation: gain −18…+6 dB, noise at 15–40 dB SNR (white or pink), 50 % band limit 3.4–7 kHz, 30 % room echo (RT60 0.2–0.6 s); WavLM features recomputed | all 37 train/val actors (`modal/apps/extract_wavlm.py --augment`) |

## Runs

| Run | Change | Training option |
|---|---|---|
| `ph_ctrl` | none (control) | — |
| `ph_vis` | phoneme supervision: training-only viseme head on the articulation branch, cross-entropy weight 0.5 | `--w-viseme 0.5` |
| `ph_bil` | extra lip error on /p b m/ frames and the 2 frames before them | `--w-bilabial 1.0` |
| `ph_aug` | degraded-audio features for half of the training samples | `--aug-prob 0.5` |
| `ph_all` | all three | |

## Motion space, validation (1,239 clips), clean and degraded speech (`modal/apps/eval_motion.py`)

| Run | Lip corr clean | Lip corr degraded | Lip amp degraded | Upper face degraded | Emotion cosine H / S / A / Su (clean) |
|---|---|---|---|---|---|
| `wl_base` (live until today) | 0.675 | 0.641 | 0.87 | 0.80 | 0.60 / 0.82 / 0.82 / 0.87 |
| `ph_ctrl` | 0.676 | 0.641 | 0.84 | 0.79 | 0.64 / 0.81 / 0.82 / 0.84 |
| `ph_vis` | 0.662 | 0.649 | 0.81 | 0.80 | 0.70 / 0.80 / 0.88 / 0.87 |
| `ph_bil` | 0.661 | 0.637 | 0.80 | 0.81 | 0.73 / 0.83 / 0.82 / 0.78 |
| `ph_aug` | 0.676 | 0.658 | **0.89** | **0.89** | 0.66 / 0.86 / 0.80 / 0.83 |
| `ph_all` | **0.685** | **0.663** | 0.77 | 0.80 | 0.62 / 0.83 / 0.79 / 0.86 |

Phoneme supervision and closure weighting alone did not help in motion space. Degraded-audio training kept accuracy on degraded speech best while keeping full amplitude.

## Rendered, 80 validation clips (A10G, per-frame streaming, emotion strength 1.5)

| Model | Mouth open corr / amp | Jaw corr / amp | Width corr | LSE-C / LSE-D | Emotion F1 | ArcFace |
|---|---|---|---|---|---|---|
| `wl_base` | 0.582 / 0.82 | 0.597 / 0.94 | 0.586 | 4.74 / 9.55 | 0.835 | 0.882 |
| **`ph_aug`** | **0.600** / 0.87 | 0.587 / 0.98 | 0.583 | **5.08 / 9.15** | 0.777 | 0.876 |
| `ph_all` | 0.593 / 0.76 | 0.590 / 0.84 | 0.594 | 5.13 / 9.12 | 0.694 | 0.877 |

Paired per clip, `ph_aug` − `wl_base` (bootstrap 95 % interval): LSE-C +0.34 [+0.09, +0.61], LSE-D −0.40 [−0.71, −0.13] (42 clips ≥ 4 s); mouth opening +0.018 [−0.002, +0.038]; jaw −0.011 and width −0.003 (not significant). This is the first statistically significant SyncNet improvement of the project.

Phoneme level (`viseme_eval.py`, 158 bilabials, 86 real full closures):

| Model | Full closures | Strict recall | Strict precision | False closures on open vowels | Inner-gap corr |
|---|---|---|---|---|---|
| `wl_base` | 120 | 0.90 | 0.64 | 8.5 % | 0.567 |
| `ph_aug` | 101 | 0.85 | **0.72** | 9.8 % | 0.581 |
| `ph_all` | 89 | 0.73 | 0.71 | 8.9 % | 0.582 |

## Decision

`ph_aug` is the live model (SHA-256 `4cc3a7359b2fdfc0a9a963f5849cd3419fe4073eeef9ae2dc261d95970ccbd00`): significantly better SyncNet, less over-closing, most robust to degraded audio, full amplitude. `ph_all` scored similar SyncNet but smaller mouth and jaw movement, emotion F1 below the 0.70 target, and closed the lips on only 3 of 15 /p b m/ in the user's recording.

Cost: phoneme labelling about $1.2, degraded features about $1.8, 5 training runs about $0.4, motion evaluation about $0.1, 2 rendered evaluations about $0.8.
