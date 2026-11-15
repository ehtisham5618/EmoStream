# Pretrained model and renderer selection

Date: 2026-11-14. Evidence: code read at the pinned commits below, and the runs in [../experiments/2026-11-14_pretrained_poc.md](../experiments/2026-11-14_pretrained_poc.md). Claims marked *(run)* were measured by us; *(code)* were read in the repository; *(paper/README)* are the authors' statements and were not verified.

## Recommendation

**Use the LivePortrait renderer as packaged in Ditto, frozen, and Ditto's motion-diffusion model as the pretrained audio-to-motion baseline. Train EmoStream's own small behaviour model in the same motion space.**

Reasons, in order of weight:

1. **It is the only candidate whose renderer is separable and cheap.** LivePortrait encodes the portrait once into an appearance volume and then needs one warp and one decode per frame, driven by a 70-number motion vector (63 expression offsets, 3 pose angles, 3 translations, scale). Anything that predicts those numbers can drive it *(code)*. That is exactly the "behaviour model + renderer with a stable interface" factorisation described by Keyframe Labs.
2. **It already works from audio.** Ditto ships a model that predicts this motion from HuBERT features, so there is a real baseline to beat rather than a blank page *(run)*.
3. **It fits the memory budget.** 4.8–5.0 GiB peak in unoptimised PyTorch *(run)*, against 9.5 GiB for Hallo2 and 16.9 GiB for AniPortrait *(run)*.
4. **It is the only one near real time.** 13.7 FPS end to end on an A10G at 1432 px with 50 diffusion steps, before any optimisation *(run)*; the others that match its quality are 40–111× slower than real time *(run)*.
5. **Licences allow academic development**, and the training code for the motion model is public (Apache-2.0) *(code)*.

What this choice does **not** give us, and therefore what EmoStream must add:

- **Low latency.** Ditto's online mode emits a block of 10 frames only after the next 10 frames of audio have arrived, because consecutive 80-frame diffusion windows are cross-faded. Each frame therefore waits 0.5–0.9 s for future audio before any computation *(code; released online config: `overlap_v2=70`, `sampling_timesteps=10`)*. The project target is p50 ≤ 350 ms.
- **Visible emotion control.** On the test portrait, Ditto's five emotion settings were nearly indistinguishable *(run, one portrait)*.
- **Intensity control.** There is none; the emotion input is a class distribution *(code)*.

## Categories

The candidates are not interchangeable. They fall into three groups.

**A. Complete audio-driven models** (portrait + audio in, video out)

| Model | How it works | Real-time path |
|---|---|---|
| SadTalker | Audio → 3DMM expression and pose coefficients (ExpNet, PoseVAE) → face-vid2vid renderer | No streaming mode; whole-clip coefficient generation |
| AniPortrait | Audio → 3D mesh + pose → landmark images → SD-1.5 video diffusion | No: 25 denoising steps per 16-frame clip through a 0.9 B-parameter UNet |
| Hallo2 | Audio → SD-1.5 video diffusion with audio cross-attention, clip-by-clip continuation | No: 40 steps per 16-frame clip |
| Ditto | Audio → motion diffusion in LivePortrait's motion space → LivePortrait renderer | Yes, with a chunked online mode (0.5–0.9 s algorithmic delay) |
| JoyVASA | Audio → motion diffusion (DiT) in LivePortrait's motion space → LivePortrait renderer | Not designed for streaming; whole-sequence sampling |

**B. Portrait renderers that need a separate motion generator**

| Model | Driving signal | Notes |
|---|---|---|
| LivePortrait | 21 implicit 3-D keypoints: canonical keypoints of the source, plus per-frame rotation, translation, scale and expression offsets | Designed for video-driven reenactment. No audio input. Ditto and JoyVASA both add an audio model on top of it. |
| SadTalker's face renderer | 3DMM coefficients mapped to face-vid2vid keypoints | Usable separately in principle, but lower resolution and tied to 3DMM fitting |

**C. Lip-sync components that need existing video frames** (not suitable for a single still image)

| Model | Why it is in this group |
|---|---|
| Wav2Lip | Repaints the mouth region of existing frames; no head motion, no expression |
| MuseTalk | Inpaints the mouth region in latent space on a source video (or a repeated still); the rest of the face does not move |
| LatentSync | Latent-diffusion lip re-synchronisation of an existing video |

Group C models can make a still image "talk" only by repeating the image as a video, which gives a moving mouth on a frozen face. They do not meet the requirement for blinks, brows, gaze and head motion, so they were not run.

## Comparison against the selection criteria

| Criterion | SadTalker | AniPortrait | Hallo2 | LivePortrait | Ditto | JoyVASA |
|---|---|---|---|---|---|---|
| Category | A | A | A | B | A (B inside) | A (B inside) |
| One portrait + raw audio | Yes *(run)* | Yes *(run)* | Yes *(run)* | No audio input | Yes *(run)* | Yes *(code)* |
| Lip sync (visual impression) | Adequate, small mouth opening | Good | Good | n/a | Good | not run |
| Full-face expression | Limited | Yes | Yes, richest | Whatever drives it | Lips, eyes, pose; other regions follow the source | Yes *(README)* |
| Head movement | Slight | Moderate | Strong | Whatever drives it | Natural, moderate | Yes *(README)* |
| Identity preservation | Good (crop only) | Good | Good | Good | Good, full frame | not run |
| English audio | Yes | Yes | Yes (English-only training) | n/a | Yes | Released motion model uses a Chinese HuBERT |
| Continuous / long output | Clip at once | Clip by clip | Designed for long video | Per frame | Yes, streaming | Whole sequence |
| Causal or continuation inference | No | No | Continuation, not causal | Per frame (stateless) | Windowed continuation with previous-motion conditioning | No |
| Peak GPU memory *(run)* | 3.4 GiB | 16.9 GiB | 9.5 GiB | within Ditto's figure | 4.8–5.0 GiB | not run |
| End-to-end speed *(run)* | 5.3 FPS (L4, incl. loading) | 0.75 FPS (A10G) | 0.22 FPS (A10G) | 13.6 ms/frame on RTX 4090 *(README)* | 5.7 FPS (T4), 13.7 FPS (A10G) | not run |
| Fits 6 GB target | Yes | No | No | Yes | Yes | likely (8 GB laptop tested *(README)*) |
| Runs on Modal | Yes *(run)* | Yes *(run)* | Yes *(run)* | Yes (inside Ditto) | Yes *(run)* | not run |
| Pretrained weights | GitHub release | Hugging Face; one dependency now missing upstream | Hugging Face | Hugging Face | Hugging Face (PyTorch, ONNX, TensorRT) | Hugging Face |
| Code licence | Apache-2.0 | Apache-2.0 | MIT | MIT | Apache-2.0 | MIT |
| Licence caveats | Third-party parts under their own terms | Stable Diffusion 1.5 weights (CreativeML OpenRAIL-M) | SD 1.5 weights; super-resolution part under S-Lab 1.0; InsightFace models | InsightFace detector/landmark models are for non-commercial research | Bundles InsightFace-derived detector and landmark ONNX models (non-commercial research) | Inherits LivePortrait's caveats |
| Fine-tuning / adaptation | Training code not released for all parts | Two-stage diffusion training, heavy | Diffusion training, heavy | Renderer frozen; drive it with own model | Training code for the motion model released (`train` branch) | Training code for the motion model released |
| Emotion input | None | None | None | n/a | 8-class distribution, weak effect in our test | None |

## Why not the others

- **SadTalker.** It works and is light, but it is an older design with a muted mouth, a tight 256 px crop, and no streaming or emotion input. Its motion space (3DMM coefficients) is less expressive than LivePortrait's, and its renderer is slower per frame for lower quality.
- **AniPortrait and Hallo2.** Best visual realism of the group, and useful as a quality reference. Both run a Stable Diffusion UNet for tens of steps per clip, which costs 40–111× real time and 9.5–16.9 GiB on an A10G. Splitting the audio into smaller pieces would not change that: the cost is per denoising step, not per clip, and both need a full clip of frames to denoise together.
- **JoyVASA.** Architecturally the closest relative of Ditto (motion diffusion over LivePortrait motion). The released motion model is trained with a Chinese HuBERT encoder and samples a whole sequence at once; Ditto offers streaming, an English-capable encoder, emotion and gaze conditions, and ONNX/TensorRT exports. Not run.
- **LivePortrait alone.** It is the renderer we use. By itself it has no audio path.

## Newer work checked but not adopted

A web search on 2026-11-14 turned up several 2025–2026 streaming talking-head papers: SoulX-FlashHead (1.3 B parameters, real time on an RTX 4090 according to the paper), DyStream (flow-matching autoregressive, dyadic), Livatar-1 (Hedra; 141 FPS on an A10 according to the paper), REST, FLOAT (flow matching in a motion latent space), KDTalker. For these we have only search-result summaries: code availability, weights and licences were **not verified**, so none of them is used in the comparison. SoulX-FlashHead at 1.3 B parameters would not fit a 6 GB target in any case. They are worth revisiting if the selected stack falls short on visual quality.

## Consequences for the design

- The motion interface is fixed by the renderer: per frame, 63 expression offsets, 3 pose angles, 3 translations and 1 scale. EmoStream's behaviour model predicts these.
- Keypoint groups are known from the renderer code: lips are keypoints 6, 12, 14, 17, 19, 20 and eyes are 11, 13, 15, 16, 18. Region-aware fusion can therefore be exact rather than heuristic.
- Audio features come from the same streaming HuBERT encoder at training and inference time, which removes any offline/online feature mismatch.
- Because the renderer is frozen, visual quality is capped by LivePortrait; large head rotations and anything outside the face crop are its known limits.
