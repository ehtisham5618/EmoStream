"""Renderer acceleration experiment: LivePortrait warp + decode in TensorRT vs PyTorch.

Uses the TensorRT engines published with Ditto (``ditto_trt_Ampere_Plus``, built with
hardware-compatibility level Ampere+, TensorRT 8.6.1) and times one warp + one decode
per frame, which is the renderer's whole per-frame cost.

    modal run modal/apps/renderer_trt.py --gpu A10G
    modal run modal/apps/renderer_trt.py --gpu L4
"""
from __future__ import annotations

import json

import modal

DITTO_COMMIT = "c3e47ee"
MODELS = "/models"
DATA = "/data"
REPO = "/opt/ditto"

app = modal.App("emostream-v2-renderer-trt")
models_vol = modal.Volume.from_name("emostream-v2-models", create_if_missing=True)
data_vol = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)

# TensorRT 8.6 links against cuDNN 8, so this image uses torch 2.1 (cuDNN 8.9) rather
# than the torch 2.5 (cuDNN 9) of the main engine image.
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.1.2", "torchvision==0.16.2", index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("tensorrt==8.6.1", "cuda-python==12.2.1", "polygraphy", "colored",
                 extra_index_url="https://pypi.nvidia.com")
    .pip_install("numpy==1.26.4", "onnxruntime-gpu==1.17.1", "mediapipe==0.10.14", "librosa==0.10.2.post1",
                 "tqdm", "filetype", "imageio==2.36.1", "imageio-ffmpeg==0.5.1",
                 "opencv-python-headless==4.10.0.84", "scikit-image", "cython==3.0.11", "einops", "scipy",
                 "huggingface_hub")
    .run_commands(f"git clone https://github.com/antgroup/ditto-talkinghead {REPO}",
                  f"cd {REPO} && git checkout {DITTO_COMMIT}")
)


@app.function(image=image, gpu="A10G", volumes={MODELS: models_vol, DATA: data_vol}, timeout=1800)
def bench(portrait: str = "eval/val/M005/portrait.png", n: int = 300) -> dict:
    import os
    import subprocess
    import sys
    import time

    import numpy as np
    import torch
    from huggingface_hub import snapshot_download

    dst = f"{MODELS}/ditto"
    if not os.path.exists(f"{dst}/ditto_trt_Ampere_Plus/decoder_fp16.engine"):
        snapshot_download("digital-avatar/ditto-talkinghead", local_dir=dst,
                          allow_patterns=["ditto_cfg/*", "ditto_trt_Ampere_Plus/*", "ditto_pytorch/**"])
        models_vol.commit()
    sys.path.insert(0, REPO)
    os.chdir(REPO)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True,
                         text=True).stdout.strip()
    res = {"gpu": gpu, "frames": n}

    from core.atomic_components.avatar_registrar import AvatarRegistrar  # noqa: F401
    from core.atomic_components.cfg import parse_cfg
    from core.atomic_components.decode_f3d import DecodeF3D
    from core.atomic_components.motion_stitch import transform_keypoint
    from core.atomic_components.warp_f3d import WarpF3D
    from stream_pipeline_online import StreamSDK

    # A registered portrait from the PyTorch stack gives real inputs for both back ends.
    sdk = StreamSDK(f"{dst}/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl", f"{dst}/ditto_pytorch")
    info = sdk.avatar_registrar(f"{DATA}/{portrait}", max_dim=1920, n_frames=1)
    f_s = info["f_s_lst"][0]
    x_s = transform_keypoint(info["x_s_info_lst"][0]).astype(np.float32)
    rng = np.random.default_rng(0)
    drives = [(x_s + rng.normal(0, 0.01, x_s.shape)).astype(np.float32) for _ in range(n)]

    def timeit(warp, dec, label):
        for d in drives[:20]:
            dec(warp(f_s, x_s, d))
        torch.cuda.synchronize()
        t = time.perf_counter()
        tw = 0.0
        for d in drives:
            t1 = time.perf_counter()
            f = warp(f_s, x_s, d)
            tw += time.perf_counter() - t1
            img = dec(f)
        torch.cuda.synchronize()
        total = time.perf_counter() - t
        res[label] = {"ms_per_frame": round(1000 * total / n, 2), "warp_ms": round(1000 * tw / n, 2),
                      "decode_ms": round(1000 * (total - tw) / n, 2), "fps": round(n / total, 1),
                      "out_shape": list(img.shape)}
        return img

    img_pt = timeit(sdk.warp_f3d, sdk.decode_f3d, "pytorch_fp16_autocast_numpy_io")

    # PyTorch with tensors kept on the GPU between warp and decode (EmoStream's engine path).
    warp_m, dec_m = sdk.warp_f3d.warp_net.model, sdk.decode_f3d.decoder.model
    fs_t, xs_t = torch.from_numpy(f_s).cuda(), torch.from_numpy(x_s).cuda()

    def run_gpu(d):
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
            out = dec_m(warp_m(fs_t, xs_t, torch.from_numpy(d).cuda()))
        return (out.float().clamp_(0, 1)[0].permute(1, 2, 0) * 255 + 0.5).to(torch.uint8).cpu().numpy()

    for d in drives[:20]:
        run_gpu(d)
    t = time.perf_counter()
    for d in drives:
        run_gpu(d)
    total = time.perf_counter() - t
    res["pytorch_fp16_gpu_resident"] = {"ms_per_frame": round(1000 * total / n, 2), "fps": round(n / total, 1)}
    res["pytorch_peak_alloc_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 3)

    try:
        trt_dir = f"{dst}/ditto_trt_Ampere_Plus"
        cfgs = parse_cfg(f"{dst}/ditto_cfg/v0.4_hubert_cfg_trt.pkl", trt_dir, None)
        warp_trt, dec_trt = WarpF3D(cfgs[4]), DecodeF3D(cfgs[5])
        img_trt = timeit(warp_trt, dec_trt, "tensorrt_fp16")
        diff = np.abs(img_trt.astype(np.float32) - img_pt.astype(np.float32))
        res["tensorrt_vs_pytorch_last_frame"] = {"mean_abs_diff_0_255": round(float(diff.mean()), 3),
                                                 "max_abs_diff_0_255": round(float(diff.max()), 1)}
    except Exception as e:  # noqa: BLE001
        import traceback

        res["tensorrt_error"] = repr(e)[:300]
        res["tensorrt_traceback"] = traceback.format_exc()[-1200:]
    smi = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    res["device_used_mib_at_end"] = int(smi.splitlines()[0])
    os.makedirs(f"{DATA}/bench/renderer", exist_ok=True)
    with open(f"{DATA}/bench/renderer/{gpu.replace(' ', '_')}.json", "w") as f:
        json.dump(res, f, indent=1)
    data_vol.commit()
    return res


@app.local_entrypoint()
def main(gpu: str = "A10G", n: int = 300):
    print(json.dumps(bench.with_options(gpu=gpu).remote(n=n), indent=1))
