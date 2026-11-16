# Experiments and ablations

Every run of this iteration, in order, with what it changed, what it showed and where its output lives. All training used the 33 training actors; all selection used the four validation actors; **the six test actors were not loaded by any job**, and their feature packs were not copied to the second workspace.

Baseline for every comparison: `reg` (frozen copy `emostream/_frozen/reg_2026-11-15/`, SHA-256 `d792adfe…7027`).

## A. Training runs

Common settings: 5,000 steps, batch 64, 5-second crops, AdamW, dropout 0.3, weight decay 0.01, one Tesla T4, about 5 minutes each. Checkpoint kept = best validation score (lip correlation + 0.5 × mean emotion-offset cosine), evaluated every 500 steps. Metrics on all 1,589 validation clips, in motion space.

| Run | Change | Best step | Lip corr | Lip amp | Upper-face amp | Head rotation std (°) | Emotion-offset cosine H / S / A / Su |
|---|---|---|---|---|---|---|---|
| `it_base` | none (reproduces `reg`) | 1,000 | 0.630 | 0.53 | 0.39 | 0.45 / 0.14 / 0.10 | 0.76 / 0.81 / 0.77 / 0.89 |
| `it_ccc` | + concordance loss (weight 1) | 1,500 | 0.654 | 0.79 | 0.79 | 0.90 / 0.44 / 0.25 | 0.77 / 0.91 / 0.78 / 0.92 |
| `it_la2` | + 2 frames look-ahead | 2,000 | 0.651 | 0.65 | 0.53 | 0.79 / 0.30 / 0.15 | 0.79 / 0.86 / 0.73 / 0.88 |
| **`it_ccc_la2`** | + both | 1,500 | **0.666** | 0.83 | 0.84 | 0.94 / 0.44 / 0.27 | 0.72 / 0.90 / 0.81 / 0.87 |
| `it_ccc_la4` | concordance + 4 frames look-ahead | 1,000 | 0.674 | 0.88 | 0.89 | 1.01 / 0.40 / 0.26 | 0.69 / 0.83 / 0.74 / 0.92 |
| `it_ccc_cap07` | concordance, lip cap 0.7 | 1,500 | 0.655 | 0.80 | 0.79 | 0.86 / 0.44 / 0.26 | 0.76 / 0.90 / 0.83 / 0.89 |
| `it_ccc_cap10` | concordance, lip cap 1.0 | 1,500 | 0.656 | 0.84 | 0.83 | 0.91 / 0.43 / 0.25 | 0.74 / 0.90 / 0.82 / 0.92 |

Real clips: head rotation std 1.16 / 0.56 / 0.32°.

Findings:

- The concordance loss is the change that matters: amplitude of lips, upper face and head all move from 25–53 % to 79–94 % of real, and lip correlation rises rather than falls.
- Look-ahead adds a little correlation (+0.012 to +0.021 for two frames). Four frames add 0.008 more for another 80 ms of delay; not selected.
- The lip cap on the emotion branch makes no measurable difference; kept at 0.35.
- In every run the validation score peaks between 1,000 and 2,000 steps and then drifts down while amplitude keeps rising (e.g. `it_ccc_la2` at 5,000 steps: lip correlation 0.660, amplitude 0.91, "angry" cosine 0.63). The saved checkpoints are the early ones. Validation has four actors, so differences of a few hundredths are noise.

Checkpoints and `report.json`: `emostream-v2-models:/emostream/<run>/` (both workspaces).

## B. Rendered-video evaluation (80 validation clips)

Generated at 512 px with the watermark on, PyTorch renderer on an A10G; scored by `modal/apps/evaluate.py`.

| Tag | Model and settings | Emotion F1 | ArcFace | Mouth corr / amp | Jaw corr / amp | LSE-C / LSE-D |
|---|---|---|---|---|---|---|
| `gt_val` | real video | 0.734 | 0.754 | — | — | 5.78 / 8.69 |
| `val_oracle` | real motion through the renderer | 0.725 | 0.890 | 0.94 / 0.94 | 0.92 / 0.96 | not run |
| `val_ditto` | Ditto | 0.212 | 0.955 | not run | not run | 4.75 / 9.17 |
| `val_emostream_reg` | `reg`, block streaming | 0.651 | 0.930 | 0.52 / 0.40 | 0.56 / 0.50 | 4.79 / 9.18 |
| `val_it_ccc_h1` | `it_ccc`, per-frame | 0.771 | 0.919 | 0.52 / 0.66 | 0.54 / 0.71 | not run |
| `val_it_ccc_h5` | `it_ccc`, block | 0.706 | 0.918 | 0.55 / 0.67 | 0.55 / 0.72 | not run |
| `val_it_ccc_la2_h1` | `it_ccc_la2`, per-frame | 0.708 | 0.915 | 0.55 / 0.74 | 0.57 / 0.80 | not run |
| `val_it_ccc_la2_h5` | `it_ccc_la2`, block | 0.754 | 0.916 | 0.57 / 0.72 | 0.58 / 0.78 | 4.76 / 9.56 |
| `val_la2_g15` | `it_ccc_la2`, block, emotion strength 1.5 | 0.811 | 0.883 | 0.58 / 0.78 | 0.57 / 0.87 | not run |
| `xc_la2_<emotion>` | `it_ccc_la2`, selected emotion forced, 20 mixed-voice clips each | see `emotion_control_evaluation.md` | 0.90–0.95 | — | — | — |

The same model scored 0.771 and 0.706 (and 0.708 and 0.754) under the two streaming modes: the emotion score has a noise band of roughly ±0.03 at this sample size.

## C. Analyses without rendering (CPU, local)

| Script | Question | Answer |
|---|---|---|
| `evaluation/benchmarks/feature_hop_check.py` | Does per-frame feature streaming change predictions? | Yes: lip correlation −0.04 to −0.06 (table in `articulation_improvement.md`) |
| `evaluation/benchmarks/emotion_control_motion.py` | Is emotion independent of the voice? Is intensity continuous? Is articulation preserved? | Yes to all three; emotion under-expressed at 29–47 % |
| Session audio through `reg` (ad hoc) | Does the model return to rest in silence? | Yes; the open mouth came from the portrait |
| Rest-pose statistics over 33 training actors (ad hoc) | Can portraits be pulled to an average neutral face? | No: between-actor spread is as large as emotion offsets |
| `evaluation/benchmarks/fake_server.py` + `browser_playback.py` | Does the client present frames evenly? | Old client: no; new: yes |

## D. Engine and live runs

| Run | Setting | Result |
|---|---|---|
| `av_offsets` | SyncNet offset on 24 real validation clips | 0 ×12, −1 ×8, −2 ×2, −3 ×1, −4 ×1 frames |
| `bench/open_asis`, `open_closed` | Open-mouthed portrait, speech with pauses, lip closing off / on | Off: mouth stays open in silence. On: closes in pauses |
| `bench/neutral_portrait` | Ordinary portrait (lip ratio 0.12), lip closing on | Natural; no distortion visible |
| A10G, TensorRT, `it_ccc_la2`, block, catch-up 450 ms | 16 s | 19.8 FPS shown, 74 of 400 frames skipped, latency 372 / 466 ms |
| L40S, `it_ccc_la2`, block | 60 s | 25 FPS, 0 skipped, latency 346 / 427 / 441 ms |
| L40S, `it_ccc_la2`, per-frame | 60 s | 25 FPS, 0 skipped, latency 257 / 278 / 319 ms |
| L40S, `it_ccc`, block | 60 s | 25 FPS, 0 skipped, latency 267 / 347 / 365 ms |
| L40S, `it_ccc_la2`, per-frame, 9 emotion changes | 300 s | 7,500 / 7,500 frames, latency 270 / 273 / 403 ms, 2.77 GiB |
| Browser against the L40S worker | 45 s, before / after client fixes | 2.8 → 23.9 frames drawn per second; voice-to-face 2,576 → 554 ms |

Latency is p50 / p95 (/ max), server side.

## E. Decisions

| Decision | Chosen | Why | Cost |
|---|---|---|---|
| Checkpoint | `it_ccc_la2` | Best mouth and jaw on rendered video; emotion at least as good | 80 ms more look-ahead than `it_ccc` |
| Live streaming | Per-frame (hop 1) on L40S | Lowest and steadiest delay, evenly spaced frames | Mouth correlation 0.55 instead of 0.57; five encoder passes per block (6.4 ms per frame) |
| Export streaming | Block (hop 5) | Most accurate; delay irrelevant offline | — |
| Emotion strength | 1.5 | F1 0.75 → 0.81; expressions clearer, undistorted | ArcFace 0.92 → 0.88 |
| Lip cap | 0.35 (unchanged) | Raising it changed nothing | — |
| Renderer | Unchanged | Oracle shows it is not the limit | — |
| A10G default | Not recommended for live | 19.8 FPS shown with skipping | — |

## F. Tried and rejected, or not tried

- **Output gain on the mouth** — not used; amplitude was restored through the loss instead.
- **Average-neutral correction of the portrait** — rejected on the data (section C).
- **Four frames of look-ahead** — rejected: small gain, 80 ms more delay.
- **Stochastic head motion, gaze model, speech-aware blinks** — not tried.
- **Training on per-frame features, 50 Hz features, a generative motion model, larger capacity** — not tried. Capacity was not increased because the halved model matched the full one in the previous iteration, and nothing here pointed to capacity.
- **Renderer replacement** — not justified by the oracle result.

## G. Cost

Workspace `ehtisham-malik5618`: seven training runs, eight generation runs, scoring, the oracle and offset checks — roughly $4, which exhausted its credit. Workspace `abdulmat40`: lip-closing tests, L40S live runs, deployment and browser tests — roughly $2. Raw MEAD preprocessing was not repeated. Figures are estimates from GPU-minutes; the Modal dashboard has the exact amounts.
