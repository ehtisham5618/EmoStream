# Behaviour model training — first runs, 2026-11-15

**Question.** Can a small causal model learn LivePortrait motion from streaming speech features and an emotion label, on MEAD, well enough to drive the renderer?

**Answer so far (motion space, validation actors only).** It learns the emotion offsets well and follows lip motion moderately. Four configurations all reach about the same place: lip correlation ≈ 0.63, emotion-offset agreement 0.7–0.9, and a mouth that moves 40–60 % as much as the real one. Whether that is good enough is decided by the rendered-video evaluation (`docs/evaluation/`), not by these numbers.

## Data

Features from `modal/apps/mead_preprocess.py`: 16,988 clips, no failures. Per clip: LivePortrait motion at 25 FPS from a fixed face crop (expression 63, rotation in degrees 3, translation, scale) and streaming-HuBERT features (1024-d at 25 FPS, the same encoder used at inference). Cost: 25,428 GPU-seconds (7.1 GPU-hours) across T4 containers, about 1.5 s per clip.

| Split | Actors | Clips | Used for |
|---|---|---|---|
| train | 33 | 13,057 | Fitting |
| val | 4 (M005, M024, W026, W035) | 1,589 | Checkpoint and configuration choice |
| test | 6 | 2,342 | Not loaded by any training code |

Targets are deltas from each actor's neutral rest pose; the articulation branch additionally has each clip's static emotional offset removed (see `emostream/training/data.py`).

## Model and loss

`BehaviourNet` (see `docs/architecture/emostream_architecture.md`): 1,361,385 parameters at hidden size 256; 556,009 at 128. Loss: L1 plus L1 on frame differences, in per-dimension standardised units with dimension weights clamped to a 10× range; AdamW, one-cycle schedule, batch 64, 5-second crops. Trained on one Tesla T4 at roughly 1,100 steps per minute.

## Runs

Metrics are on all 1,589 validation clips, processed as a stream:

- **lip corr** — Pearson correlation between predicted and real motion on the lip coordinates that move.
- **lip energy** — predicted mean frame-to-frame lip movement divided by the real one (1.0 = as lively as real).
- **offset cos** — cosine similarity between predicted and real mean expression offset from neutral, level-3 clips, per emotion.
- **pose MAE** — head rotation error in degrees.

| Run | Change from `base` | Steps | Best step (by score) | Lip corr | Lip energy | Pose MAE | Offset cos happy / sad / angry / surprised |
|---|---|---|---|---|---|---|---|
| `base` | dropout 0.1, weight decay 1e-4 | 12,000 | 3,000 | 0.613 | 0.45 | 2.53° | 0.75 / 0.93 / 0.76 / 0.88 |
| `reg` | dropout 0.3, weight decay 1e-2 | 5,000 | 1,000 | 0.630 | 0.40 | 2.27° | 0.76 / 0.81 / 0.77 / 0.89 |
| `small` | as `reg`, hidden 128 | 5,000 | 4,500 | 0.627 | 0.47 | 2.56° | 0.77 / 0.90 / 0.69 / 0.86 |
| `joint` | as `reg`, branches trained jointly (ablation) | 5,000 | 4,500 | 0.610 | 0.45 | 2.63° | 0.76 / 0.90 / 0.78 / 0.90 |

Score = lip corr + 0.5 × mean offset cos. The `base` run's saved checkpoint was chosen by lip MAE (step 1,000: lip corr 0.641, offset cos 0.68 / 0.76 / 0.69 / 0.85), before the selection rule was changed; the table row shows where the score would have picked.

## Observations

1. **Lip correlation peaks early and then declines** in `base` (0.641 at step 1,000 → 0.576 at 12,000) while training loss keeps falling. The articulation branch overfits the 33 training actors. Stronger dropout and weight decay flatten the decline but do not raise the peak.
2. **The mouth is muted.** Lip energy stays between 0.40 and 0.62. This is the expected effect of an L1 regression: where the audio does not determine the motion exactly, the model predicts the average.
3. **Emotion offsets are learned.** Agreement with the real offsets reaches 0.7–0.95 on unseen actors. "Sad" and "surprised" are the clearest; "angry" and "happy" are lower and vary between checkpoints.
4. **Halving the width costs nothing measurable** (`small`: 0.56 M parameters, same metrics).
5. **Separate vs joint branch training** gives nearly the same motion-space numbers. The motion metrics here cannot show the difference the separation was designed for (whether the explicit emotion control stays effective when voice and selected emotion disagree); that needs a cross-conditioning test on rendered video.
6. **Chunked streaming equals whole-sequence processing**: maximum absolute difference 3e-7 to 1e-6 at chunk sizes of 1, 5 and 10 frames, on every run.
7. Validation has only four actors, so differences of a few hundredths between runs are within noise.

## Not done yet

- Head motion is regressed and therefore calm; no stochastic head-motion component has been trained.
- No comparison of speech encoders (only Ditto's streaming HuBERT was used).
- No test-split evaluation.

## Reproduce

```
modal run modal/apps/mead_preprocess.py                        # features + per-actor packs
modal run modal/apps/train_behaviour.py --run base
modal run modal/apps/train_behaviour.py --run reg   --steps 5000 --dropout 0.3 --weight-decay 0.01
modal run modal/apps/train_behaviour.py --run small --steps 5000 --dropout 0.3 --weight-decay 0.01 --hidden 128
modal run modal/apps/train_behaviour.py --run joint --steps 5000 --dropout 0.3 --weight-decay 0.01 --no-separate-branches
```

Checkpoints and `report.json` are in `emostream-v2-models:/emostream/<run>/`.
