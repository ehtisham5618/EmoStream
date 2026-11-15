# Streaming engine and renderer speed — 2026-11-14

**Question.** With the selected stack (frozen LivePortrait renderer, Ditto's motion model as the pretrained behaviour baseline), how fast is EmoStream's own streaming engine, where does the time go, and what does it take to reach 25 FPS?

**Answer.** The renderer is the bottleneck. In PyTorch it needs 47–52 ms per frame on an A10G and 174 ms on a T4. Ditto's published TensorRT engines bring the A10G to 40.0 ms per frame, exactly 25 FPS for rendering alone, with visually identical output. Ditto's motion model adds 28 ms per frame on top; a lighter behaviour model is needed to stay at 25 FPS end to end.

## Engine runs (`modal/apps/engine_bench.py`)

EmoStream's engine (`emostream/engine/`), Ditto motion model with its released online settings (10 diffusion steps, 10-frame blocks), 512×512 crop output, watermark on, audio fed in 200 ms chunks at microphone pace. All frames expected were produced (the tail is flushed).

| GPU | Input | Frames | Motion model | Renderer | Stitch | Total | Peak GPU memory |
|---|---|---|---|---|---|---|---|
| T4 | painted portrait, 15.8 s | 394 / 394 | 43.9 ms/frame | 174.2 ms/frame | 1.3 ms | 4.55 FPS | 4.20 GiB device, 1.59 GiB PyTorch reserved |
| A10G | MEAD actor M005, 3 s clip | 75 / 75 | 27.7 ms/frame | 46.6 ms/frame | 0.6 ms | 13.3 FPS | 4.39 GiB device |

Because both runs were slower than real time, frames fell progressively behind the audio (median latency 2.5 s on the A10G over a 3 s clip, 36 s on the T4 over 15.8 s). Those latency figures only show that the configuration cannot keep up; they are not a latency result.

An L4 run was attempted twice and never started: no L4 capacity was available in the workspace's region for more than ten minutes each time.

**Algorithmic delay of the baseline.** Independent of hardware, Ditto's online mode emits a 10-frame block only after the following 10 frames have arrived, plus 85 ms of encoder look-ahead: 520–880 ms before any computation. This is a property of the method (read from the code and confirmed by the engine's bookkeeping), and it alone exceeds the project's 350 ms median target.

## Renderer back ends (`modal/apps/renderer_trt.py`)

One warp plus one decode per frame, 300 frames after 20 warm-up frames, A10G, portrait M005.

| Back end | Warp | Decode | Per frame | FPS |
|---|---|---|---|---|
| PyTorch, fp16 autocast, NumPy between stages (Ditto's wrappers) | 23.7 ms | 31.4 ms | 55.1 ms | 18.2 |
| PyTorch, fp16 autocast, tensors kept on the GPU (EmoStream engine path) | — | — | 51.5 ms | 19.4 |
| TensorRT 8.6.1 fp16 (Ditto's published `Ampere_Plus` engines) | 15.0 ms | 25.0 ms | 40.0 ms | 25.0 |

TensorRT against PyTorch on the same frame: mean absolute difference 0.14 on a 0–255 scale, maximum 17.2 (isolated pixels). Device memory in use at the end of the run, with both back ends loaded, was 2.26 GiB.

Notes:

- The TensorRT image needs torch 2.1 (cuDNN 8) instead of the main image's torch 2.5 (cuDNN 9), because TensorRT 8.6 links against cuDNN 8.
- The engines are built for Ampere-or-newer GPUs, so they cannot run on a T4.
- TensorRT is not yet wired into the EmoStream engine; the engine numbers above are PyTorch.

## What follows from this

| Configuration on A10G | Motion | Render | Sum | Frames per second |
|---|---|---|---|---|
| Ditto motion + PyTorch renderer (measured) | 27.7 | 46.6 | 74.9 ms | 13.3 |
| Ditto motion + TensorRT renderer (sum of measured parts) | 27.7 | 40.0 | 67.7 ms | ~14.8 |
| Light behaviour model (~1 ms) + PyTorch renderer (projection) | ~1 | 46.6–51.5 | ~48–53 ms | ~19–21 |
| Light behaviour model + TensorRT renderer (projection) | ~1 | 40.0 | ~41 ms | ~24 |

The last two rows are projections from measured parts, not measurements; the EmoStream model's own cost is measured in the evaluation runs.

On the project's reference GPU (RTX 4050 laptop, 6 GB) nothing was measured, because that hardware is not available on Modal. Memory is within the 6 GB budget on every GPU tested; speed on that card is unknown.

## Emotion input of the baseline, on a real face

Ditto was run on MEAD validation actor M005 (neutral portrait, neutral speech) with emotion set to neutral, happy and angry through its own stitcher, and neutral, happy, sad, angry and surprised with EmoStream's full-face path (all 63 expression coordinates applied instead of lips and eyes only).

Result, from frame sheets: the outputs are again hard to tell apart. Full-face driving did not make the emotions clearly visible either; "surprised" opens the mouth somewhat wider and that is the only consistent difference. Together with the painted-portrait test, this is two portraits on which Ditto's emotion condition has little visible effect. It has not been scored with an emotion classifier yet.
