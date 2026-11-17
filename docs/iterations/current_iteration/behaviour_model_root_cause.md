# Why lip sync is weak: measurements, 17 November 2026

The user's complaint after session 5: playback is smooth now, but the mouth does not correspond to the words. Each possible cause was measured separately before any retraining. All model measurements use the four validation actors (M005, M024, W026, W035); the six test actors were not loaded.

## 1. Is the model reacting less to microphone audio than to MEAD audio?

`evaluation/benchmarks/mic_domain_check.py` (current checkpoint `it_ccc_la2`, CPU). Lip-keypoint motion predicted while speech is present:

| Audio | Lip std during speech | Lip speed during speech |
|---|---|---|
| MEAD studio clips (6, actor M005) | 0.00129–0.00210, mean 0.00164 | 0.00032–0.00063 |
| User session 3 (browser microphone) | 0.00165 | 0.00045 |
| User session 4 | 0.00151 | 0.00031 |
| Same sessions raised to studio loudness | unchanged | unchanged |

**No.** Browser capture (noise suppression, automatic gain) does not mute the model.

## 2. Are speech features and mouth targets misaligned?

`evaluation/benchmarks/lip_timing_analysis.py`, 480 validation clips, 51,511 frames. A ridge regression predicts mouth opening at frame t from the stored speech feature of frame t + d:

| d (frames) | −3 | −2 | −1 | **0** | +1 | +2 | +3 | +4 | +6 |
|---|---|---|---|---|---|---|---|---|---|
| probe correlation | 0.426 | 0.490 | 0.538 | **0.559** | 0.553 | 0.526 | 0.490 | 0.446 | 0.351 |

**No.** The best feature is the frame's own. A window of past features plus d future frames: 0.597 (d = 0), 0.612 (2), 0.610 (3), 0.604 (4), 0.565 (6). Look-ahead beyond 2 frames adds nothing; the current model uses 2.

## 3. Is the model early or late?

Same clips; per clip, the shift that best aligns predicted with real mouth opening (±8 frames):

| Checkpoint | Median / mean lag (frames) | Corr at lag 0 | Corr at best lag | Mouth closures reproduced | Opening amplitude |
|---|---|---|---|---|---|
| `reg` (original) | 0 / +0.14 | 0.648 | 0.724 | 76.8 % | 0.59 |
| `it_ccc` | 0 / +0.03 | 0.671 | 0.752 | 77.8 % | 0.87 |
| **`it_ccc_la2` (live)** | 0 / −0.32 | 0.678 | 0.768 | 78.4 % | 0.91 |
| `it_ccc_la4` | 0 / −0.15 | 0.682 | 0.760 | 79.1 % | 0.95 |

**No systematic offset.** The live model is on average 13 ms early, within one frame for 69 % of clips. The gap between correlation at lag 0 and at the best lag (0.68 vs 0.77) shows per-clip timing jitter of about ±1 frame, not a constant delay. About 22 % of real mouth closures are missed.

## 4. Does the live streaming mode cost accuracy?

Live serving computes one speech-encoder window per frame and reads one of its five positions ("slot"); training features came from blocks of five, so from all slots. 12 clips of M005 with ground truth (`feature_hop_check.py --positions`):

| Features | Lip correlation | Extra delay |
|---|---|---|
| Stored training features | 0.644 | — |
| Blocks of five, recomputed | 0.623 | 0–160 ms, uneven |
| Per frame, slot 0 | 0.631 | +160 ms |
| Per frame, slot 2 | 0.615 | +80 ms |
| Per frame, slot 3 | 0.607 | +40 ms |
| **Per frame, slot 4 (live)** | 0.592 | — |

On **rendered** video the gain mostly disappears (80 validation clips, emotion strength 1.5, A10G, `modal/apps/evaluate.py`):

| Live read-out | Mouth opening corr / amp | Jaw corr / amp | LSE-C / LSE-D (42 clips ≥ 4 s) | Emotion F1 | ArcFace |
|---|---|---|---|---|---|
| slot 4 (live) | 0.546 / 0.81 | 0.563 / 0.89 | 4.89 / 9.43 | 0.77 | 0.882 |
| slot 2 | 0.570 / 0.78 | 0.567 / 0.86 | 4.77 / 9.48 | 0.84 | 0.884 |
| slot 0 | 0.570 / 0.76 | 0.563 / 0.85 | 4.58 / 9.61 | 0.80 | 0.881 |

Differences are within noise (LSE-C standard error about 0.14; emotion F1 about ±0.03–0.05 at this size). **Decision: slot 4 kept**; no proven benefit justifies more delay.

## 5. Do better training losses help?

Four T4 runs, 5,000 steps each, otherwise identical to `it_ccc_la2` (`modal/apps/train_behaviour.py`):

| Run | Change | Best lip corr | Opening amp | Upper face |
|---|---|---|---|---|
| `lt_base` | none (control) | 0.666 | 0.83 | 0.84 |
| `lt_vccc` | + concordance of lip velocities | 0.656 | 0.94 | 0.86 |
| `lt_close` | + extra weight on closed-mouth frames | 0.657 | 0.89 | 0.86 |
| `lt_both` | both | 0.668 | 0.90 | 0.83 |

**No.** All within noise; the control reproduced the current model exactly (0.6657, step 1,500). Validation peaks at 1,000–2,000 steps in every run and then declines (over-fitting to 33 training actors).

## 6. Do the speech features carry enough information?

`evaluation/benchmarks/feature_encoder_probe.py`: 40 validation clips of M005 with real motion, ridge from a feature window (t−4 … t+2) to all lip coordinates, two-fold. Best layer per encoder:

| Encoder | Full context | Live context (1 s past, 80 ms future, blocks of 5) | Live context, one window per frame |
|---|---|---|---|
| **Ditto streaming HuBERT (current)** | 0.304 | 0.304 | 0.304 |
| WavLM-base-plus, layer 6 | 0.408 | **0.384** | 0.346 |
| Whisper-base encoder, layer 3 | 0.440 | 0.382 | not run (needs a 30 s input per window) |
| wav2vec2-base-960h, layer 4 | 0.395 | 0.308 | not run |

**This is the main finding.** The losses and the timing were not the bottleneck; the speech representation is. WavLM keeps most of its advantage under live constraints and is small enough (95 M parameters) to run once per frame.

Caveat: one actor, 40 clips, a linear probe. Whether a trained model gains as much has to be shown by training and rendering, and is being tested (`modal/apps/extract_wavlm.py`, `emostream/audio/wavlm.py`).

## What was not done

- No phoneme alignment; "closures reproduced" is a proxy (the most closed 15 % of each clip's real frames).
- Lip rounding is not measured separately; the mouth-width metric covers part of it.
- The test split was not used.

## 7. Data finding: MEAD audio and video numbering differ for 13 actors

Training a new speech encoder needs each clip's audio. MEAD ships audio separately (`audio.tar`, all levels; the raw volume's `extracted/` copy had level 1 only). On M005 the `.m4a` is identical to the video's soundtrack (0 ms offset, correlation 1.00, about 19 ms shorter). But for 13 actors (M037, M040, M041, W023, W025, W026, W028, W029, W033, W035, W037, W038, W040) only about 50 of 400 clips pair correctly by file number; the rest of the same-numbered files are **different sentences** (`evaluation/benchmarks/mead_audio_pairing.py`).

Every clip was therefore paired by content (`evaluation/benchmarks/mead_audio_match.py`): by number when the duration agrees, otherwise by an unambiguous duration match in the same emotion and level, and in both cases verified by running Ditto's HuBERT on the `.m4a` and correlating with the features stored from the video's own audio (right pair ≥ 0.974; 46 candidate pairs failed and were dropped).

| | Clips |
|---|---|
| Train + validation clips | 14,646 |
| Paired and verified | 12,247 (84 %) |
| Left out of WavLM training | 2,399 |
| Validation actors affected | W026 (148 left out), W035 (202 left out) |

Earlier models are unaffected: their features came from each video's own soundtrack. For a fair comparison, the Ditto-HuBERT control is trained on the same 12,247 clips (`--only-valid-wavlm`).
