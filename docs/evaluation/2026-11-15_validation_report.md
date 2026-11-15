# Evaluation report — validation actors, 2026-11-15

All numbers here are on the **validation** split (actors M005, M024, W026, W035, none seen in training). They were used to choose the model, so they are selection evidence, not a final result. **The test split (six actors) has not been evaluated.**

## Summary against the project targets

| Target (from the FYP report) | Result | Met? | Conditions |
|---|---|---|---|
| Output ≥ 256×256 | 512×512 | Yes | — |
| 25 FPS (gate: 15 FPS) | 25.0 FPS delivered, no skipped frames | Yes on L40S; gate only on A10G | L40S, TensorRT renderer, our model. A10G: 23.4 FPS of compute. **RTX 4050 not tested.** |
| Peak VRAM ≤ 6 GB | 2.77 GiB device peak | Yes on the GPUs tested | L40S / A10G, TensorRT. The 6 GB card itself was not available. |
| Latency p50 ≤ 350 ms | 269 ms | Yes | Engine-side, L40S, audio fed at microphone pace, five-minute run |
| Latency p95 ≤ 500 ms | 319 ms | Yes | Same run. Network time is extra (see §4). |
| Five-minute stability | 7,500 / 7,500 frames, no drift | Yes | Same run |
| Emotion macro-F1 ≥ 0.70 | 0.65 | **No** | Classifier scores 0.73 on real MEAD video, so 0.70 is close to its ceiling |
| Emotion gain ≥ 10 points over baseline | +44 points (0.65 vs 0.21) | Yes | Baseline = Ditto with the same emotion labels |
| ArcFace identity ≥ 0.80 | 0.93 mean, 0.89 minimum | Yes | Portrait vs generated frames |
| Lip sync within 5 % of best local baseline | LSE-C 4.79 vs 4.75 (+1 %) | Yes | Baseline = Ditto; real video scores 5.78 |
| Boundary jerk −20 % at emotion changes | −84 % | Yes | Motion space, transition gate of 10 frames vs hard switch |

## 1. Rendered-video metrics

Setup: for each validation actor and each emotion, four clips (level 3 for the four emotions, 80 clips, 8,247 frames in total). The actor's neutral still is animated with the clip's own audio and the clip's emotion label, at 512×512 with the watermark on, exactly as the product outputs it. Generation ran on an A10G with the PyTorch renderer. Scoring: `modal/apps/evaluate.py`.

| | Real MEAD video | Ditto (pretrained baseline) | EmoStream (`reg`) |
|---|---|---|---|
| Emotion macro-F1 (5 classes) | 0.734 | 0.212 | **0.651** |
| Emotion accuracy | 0.750 | 0.212 | 0.650 |
| F1 neutral / happy / sad / angry / surprised | 0.48 / 0.84 / 0.86 / 0.68 / 0.81 | 0.12 / 0.55 / 0.23 / 0.16 / 0.00 | 0.40 / 0.58 / 0.86 / 0.65 / 0.77 |
| ArcFace similarity to the portrait, mean (min) | 0.754 (0.605) | 0.955 (0.931) | 0.930 (0.894) |
| SyncNet LSE-C ↑ (42 clips) | 5.78 | 4.75 | 4.79 |
| SyncNet LSE-D ↓ (42 clips) | 8.69 | 9.17 | 9.18 |
| Behaviour-model time per frame | — | 28.9 ms | 2.5 ms |

How to read this:

- **Emotion.** The classifier is HSEmotion (`enet_b2_8`, trained on AffectNet) applied to 12 frames per clip, restricted to the five project emotions. Chance is 0.20. On real MEAD clips it reaches 0.73; that is the practical ceiling, mostly because it is unsure about neutral speech (5 of 16 real neutral clips correct). Ditto's output is at chance: its emotion input has no measurable effect, which matches what the frame sheets showed. EmoStream reaches 0.65.
- **Where EmoStream loses points.** Neutral clips are often read as happy (11 of 16) and some angry clips as happy (6 of 16): the mouth shapes our model produces while speaking show teeth, which this classifier associates with smiling. Sad (12 of 16), happy (16 of 16) and surprised (10 of 16) are recognised.
- **Identity.** Both models stay very close to the portrait. Real video scores lower (0.75) because real expressions and head movement are larger; a higher number here means "changed the face less", not "better". EmoStream's slightly lower value than Ditto's reflects that it actually moves brows and cheeks.
- **Lip sync.** SyncNet's own pipeline rejects clips under four seconds, so 38 of the 80 clips were not scored; they are the same 38 for all three columns. On the remaining 42, EmoStream and Ditto are equal within noise, and both are about 1.0 LSE-C below real video.

Confusion matrices (rows = true label, columns = predicted; order neutral, happy, sad, angry, surprised):

```
Real MEAD            Ditto                EmoStream (reg)
 5  4  0  4  3        1  0  3  7  5        4 11  0  1  0
 0 16  0  0  0        0  8  4  2  2        0 16  0  0  0
 0  0 12  4  0        0  0  4  9  3        0  3 12  1  0
 0  2  0 14  0        0  5  4  4  3        0  6  0 10  0
 0  0  0  3 13        0  0  4 12  0        0  3  0  3 10
```

## 2. Real-time performance

`modal/apps/live_bench.py`: the full engine, EmoStream model `reg`, 512×512, watermark on, audio delivered in 200 ms chunks at the pace a microphone would deliver it. Latency = arrival of a frame's last audio sample → frame available, measured after the first second.

| GPU | Renderer | Run length | Frames shown | FPS shown | Latency p50 / p95 / max | Peak GPU memory | Per frame: model / render |
|---|---|---|---|---|---|---|---|
| L40S | TensorRT fp16 | 300 s | 7,500 / 7,500 | 24.98 | 269 / 319 / 421 ms | 2.77 GiB | 1.7 / 19.5 ms |
| L40S | TensorRT fp16 | 60 s | 1,500 / 1,500 | 24.91 | 267 / 311 / 388 ms | 2.77 GiB | 1.6 / 19.1 ms |
| A10G | TensorRT fp16, catch-up on (350 ms) | 60 s | 1,139 / 1,500 | 18.87 | 311 / 390 / 470 ms | 2.56 GiB | 2.4 / 32.8 ms |
| A10G | TensorRT fp16, catch-up off, video encoding in the loop | 15.8 s | 394 / 394 | 21.86 | falls behind (p50 1.35 s) | 2.54 GiB | 2.4 / 39.7 ms |

- On the L40S the engine has headroom (46 FPS of compute) and holds 25 FPS with a median delay of 269 ms.
- The five-minute run shows no drift: median latency per minute was 269.7, 268.9, 267.9, 270.4, 266.8 ms; 1,500 frames in every minute; memory flat. Nine emotion changes were scheduled during the run.
- On the A10G the renderer alone takes about 40 ms, so the engine is just under real time. With catch-up enabled it stays within the latency targets by skipping about a quarter of the frames. A 350 ms threshold is strict given 120–280 ms of unavoidable algorithmic delay; the deployed default is 450 ms.
- Of the 269 ms median, 120–280 ms is algorithmic (85 ms of encoder look-ahead plus up to 200 ms waiting for a five-frame block) and roughly 20 ms is compute.

Not measured: the RTX 4050 laptop GPU named in the project report. Memory use (2.8 GiB) leaves ample room on a 6 GB card; speed on it is unknown and would be lower than on the A10G.

## 3. Emotion transitions

`evaluation/benchmarks/transition_jerk.py`, CPU, model `reg`, 40 neutral-speech clips of validation actor M005; the emotion switches from neutral to the target at mid-clip. Boundary jerk is the mean absolute third difference of the predicted expression (standardised units) within ±5 frames of the switch.

| Transition gate | Boundary jerk, hard switch | With gate | Reduction |
|---|---|---|---|
| 5 frames (200 ms) | 2,662–2,703 | 656–668 | 75.4 % |
| 10 frames (400 ms) — engine default | 2,662–2,703 | 421–424 | 84.2 % |
| 15 frames (600 ms) | 2,662–2,703 | 388–390 | 85.5 % |

Jerk away from any switch is 322 in the same units, so a hard switch is about eight times rougher than ordinary speech motion and the gated transition is about 1.3 times. This is measured on predicted motion, not on rendered pixels, and no human rating was collected.

## 4. Deployed application

`modal deploy modal/apps/serve.py` (L40S, TensorRT), then `evaluation/benchmarks/ws_client.py` from a laptop in Pakistan to the worker in US-East: 30 s of speech at microphone pace, emotion switched to happy half-way.

| | |
|---|---|
| Frames received | 747 of 750, in order (3 skipped by the server's catch-up) |
| Frame rate received | 25.4 FPS |
| Portrait registration | 3.5 s |
| Server-side latency p50 / p95 / max | 267 / 310 / 525 ms |
| Client round trip p50 / p95 / max | 570 / 701 / 1,191 ms |
| Emotion change | Acknowledged at frame 375; frames after it show a clear smile |
| Frontend | Served from the same URL (HTTP 200) |

The client round trip is the server latency plus two network legs between Pakistan and US-East (about 300 ms together). A worker in a nearer region would bring it close to the server figure. The app was stopped after the test; nothing is left running.

## 5. What has not been evaluated

- The **test split**. It is reserved for the final report and must be run once, after model work stops.
- Any **human rating** (naturalness, transition smoothness, emotion recognisability by people).
- **FID/KID/LPIPS** visual-quality metrics.
- **Cross-conditioning**: selected emotion different from the emotion in the voice. All clips here used the clip's own label.
- **Intensity**: only full intensity (level 3) was scored; intermediate values were not.
- The live path in a **real browser with a real microphone** (the WebSocket client reproduces the protocol, not the browser's audio capture).
- The **RTX 4050** target hardware.

## Data

Per-clip scores: `emostream-v2-data:/eval_out/{gt_val,val_ditto,val_emostream_reg}/scores.json`. Benchmarks: `emostream-v2-data:/bench/live_*/stats.json`. Transition jerk: [`data/transition_jerk_reg_M005.json`](data/transition_jerk_reg_M005.json).
