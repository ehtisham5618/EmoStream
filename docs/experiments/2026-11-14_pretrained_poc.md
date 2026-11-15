# Pretrained-model proof of concept — 2026-11-14

**Question.** Can a released, pretrained model turn one portrait plus one audio clip into a usable talking-head video, and what does each candidate cost in time and GPU memory?

**Answer.** Yes for all four that take audio. SadTalker, Ditto, AniPortrait and Hallo2 each produced a real video from the same inputs with their released weights. Only Ditto and SadTalker are within reach of real time; AniPortrait and Hallo2 are 40× and 111× slower than real time on an A10G.

## Inputs (same for every model)

| | |
|---|---|
| Portrait | `example/image.png` from the Ditto repository, 1432×1432, a painted young woman, frontal, smiling |
| Audio | `example/audio.wav` from the Ditto repository, 15.755 s, 24 kHz mono PCM16, English female speech |
| Location | Modal volume `emostream-v2-data`, `poc/inputs/` |

The portrait is a painting, not a photograph, and it is already smiling. Both facts matter for the emotion result below. Real-face inputs from MEAD validation actors were prepared afterwards for the engine benchmarks.

## How it was measured

- Each model ran inside a Modal GPU container from its own repository at a pinned commit, using its own inference script (apps in `modal/apps/poc_*.py`).
- **Peak GPU memory** is whole-device memory sampled from `nvidia-smi` every 0.25 s, so it includes every framework in the process (PyTorch, ONNX Runtime, CUDA context).
- **Wall time** for SadTalker, AniPortrait and Hallo2 is the full CLI process: start-up, model loading, preprocessing, generation and encoding. For Ditto the models were loaded once and generation was timed twice; the second run is reported.
- Frames were counted with `ffprobe -count_frames` on the output file.
- Not measured here: lip-sync scores, identity similarity, latency. Those belong to the evaluation phase and use real-face inputs.

## Results

| Model | Commit | GPU | Output | Frames | Wall time | End-to-end FPS | × real time | Peak GPU memory |
|---|---|---|---|---|---|---|---|---|
| SadTalker (256, crop) | `cd4c046` | L4 | 256×256 @ 25 | 393 | 74.7 s (CLI) | 5.3 | 4.7× slower | 3.40 GiB |
| Ditto, offline, 50 steps | `c3e47ee` | T4 | 1432×1432 @ 25 | 394 | 69.0 s | 5.7 | 4.4× slower | 4.81 GiB |
| Ditto, offline, 50 steps | `c3e47ee` | A10G | 1432×1432 @ 25 | 394 | 28.3–28.8 s | 13.7–13.9 | 1.8× slower | 4.96–4.97 GiB |
| Ditto, online mode, 50 steps, 70-frame blocks | `c3e47ee` | A10G | 1432×1432 @ 25 | 340 | 25.5 s | 13.3 | 1.6× slower | 5.01 GiB |
| AniPortrait (512, 25 steps, frame interpolation) | `7f6593f` | A10G | 512×512 @ 30 (grid 1544×516) | 472 | 629 s (CLI) | 0.75 | 40× slower | 16.87 GiB |
| Hallo2 (512, 40 steps) | `58a9aa6` | A10G | 512×512 @ 25 | 394 | 1755 s (CLI) | 0.22 | 111× slower | 9.48 GiB |

Notes on the numbers:

- SadTalker's own progress bar shows its face-render loop at 197 batches of 2 frames in 35 s, i.e. about 11 FPS for rendering alone on the L4. The rest of the 74.7 s is model loading, 3DMM fitting and audio-to-coefficient inference.
- Ditto's figures are unoptimised PyTorch, at the portrait's full 1432×1432 resolution with paste-back, with 50 diffusion steps. Its released online configuration uses 10 steps, and TensorRT engines are published; neither was used in this table.
- The online-mode run only switched `online_mode` on and kept the offline block size (70 new frames per window). With those settings Ditto's own `inference.py` wrote 340 frames instead of 394: the last 54 frames (2.2 s) of speech were never rendered. EmoStream's engine re-implements the loop with an explicit end-of-stream flush (`emostream/engine/behaviour.py`).
- Ditto's first run in each container was slower (81.9 s on the T4, about 40 s on the A10G) because of warm-up.
- The first Ditto attempt waited more than eight minutes for an L4 that never became available; the function now lists fallback GPUs.

## Visual assessment

Judged from contact sheets of 14 evenly spaced frames per output (`outputs/poc/*/`, not committed). This is one portrait and one reviewer, so it is an impression, not a measurement.

| Model | Lips | Head motion | Blinks / eyes | Identity | Artefacts |
|---|---|---|---|---|---|
| SadTalker | Moves with speech, small opening | Slight | Present | Kept, tight crop only | Soft, low resolution |
| Ditto | Clear articulation, wider opening | Visible tilts and turns | Blinks from a built-in blink schedule | Kept, full frame via paste-back | None obvious on this portrait |
| AniPortrait | Good | Moderate | Present | Kept | Slight texture shimmer across frames |
| Hallo2 | Good | Strong, including shoulders | Clear blinks | Kept | Best overall realism |

## Emotion input (Ditto)

Ditto was run with its emotion index set to neutral, happy, sad, angry and surprised (`--emo 4/3/5/0/6`). On this portrait the five outputs are **nearly indistinguishable**: the face stays smiling in all of them, including "sad" and "angry".

Two reasons are visible in the code. Motion is applied relative to the source (`x_d = x_s + (d − d0)` in `motion_stitch.py`), so the source's own smile persists. And outside the lip and eye keypoints the expression is taken from the source (`_fix_exp_for_x_d_info_v2` keeps source values for the other keypoints), so the emotion signal can only act through lips, eyes and pose.

This result is on one smiling, painted portrait. It needs to be repeated on neutral real faces before concluding that Ditto's emotion control is weak in general, but it already shows that explicit, strong emotion control is not something the baseline delivers for free.

## Issues met while reproducing

| Model | Issue | Resolution |
|---|---|---|
| Ditto | `onnxruntime-gpu==1.20.1` does not exist | Pinned 1.20.2 |
| AniPortrait | `av==11.0.0` builds from source and fails; `torchsde==0.2.5` unresolved | `av==12.1.0`; dropped `torchsde`/`torchdiffeq` (not used by `audio2vid`) |
| AniPortrait | The official source of the CLIP image encoder, `lambdalabs/sd-image-variations-diffusers`, is an empty repository on Hugging Face (only README and .gitattributes) | Used the identical folder mirrored in `BadToBest/EchoMimic` |
| AniPortrait | `xformers==0.0.22` in its requirements needs torch 2.1, while torch 2.0.1 is pinned | `xformers==0.0.21` |
| SadTalker | Requirements pin torch 1.12 / Python 3.8 | Ran on Python 3.10, torch 2.0.1 + cu118 with otherwise original pins |

## Reproduce

```
modal run modal/apps/poc_sadtalker.py
modal run modal/apps/poc_ditto.py                      # add --online, or --emo 3 --tag happy
modal run modal/apps/poc_aniportrait.py
modal run modal/apps/poc_hallo2.py
```

Outputs and per-run JSON land in `emostream-v2-data:/poc/outputs/<model>/`.
