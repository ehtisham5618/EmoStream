"""Proof of concept: AniPortrait (Zejun-Yang/AniPortrait, Apache-2.0) on a Modal GPU.

Runs the repository's own ``scripts/audio2vid.py``: audio -> 3D face mesh + head
pose (audio2mesh / audio2pose) -> projected landmark images -> Stable Diffusion
1.5 based video diffusion renderer.

    modal run modal/apps/poc_aniportrait.py
"""
from __future__ import annotations

import json
from pathlib import Path

import modal

COMMIT = "7f6593f"
MODELS = "/models"
DATA = "/data"
REPO = "/opt/AniPortrait"

app = modal.App("emostream-v2-poc-aniportrait")
models_vol = modal.Volume.from_name("emostream-v2-models", create_if_missing=True)
data_vol = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.0.1", "torchvision==0.15.2", "torchaudio==2.0.2",
                 index_url="https://download.pytorch.org/whl/cu118")
    .pip_install(
        "accelerate==0.21.0", "av==12.1.0", "decord==0.6.0", "diffusers==0.24.0", "einops==0.4.1",
        "imageio==2.33.0", "imageio-ffmpeg==0.4.9", "numpy==1.24.4", "omegaconf==2.2.3",
        "onnxruntime-gpu==1.16.3", "open-clip-torch==2.20.0", "opencv-contrib-python-headless==4.8.1.78",
        "Pillow==9.5.0", "scikit-image==0.21.0", "scikit-learn==1.3.2", "scipy==1.11.4",
        "torchmetrics==1.2.1", "tqdm==4.66.1",
        "transformers==4.30.2", "xformers==0.0.21", "controlnet-aux==0.0.7", "mediapipe==0.10.11",
        "librosa==0.9.2", "ffmpeg-python==0.2.0", "huggingface_hub==0.19.4", "pyyaml",
    )
    .run_commands(f"git clone https://github.com/Zejun-Yang/AniPortrait {REPO}",
                  f"cd {REPO} && git checkout {COMMIT}")
    .add_local_file(str(Path(__file__).parent / "_bench.py"), "/root/_bench.py")
)


def _weights(store: str):
    import os

    from huggingface_hub import snapshot_download

    if os.path.exists(f"{store}/.complete"):
        return
    snapshot_download("ZJYang/AniPortrait", local_dir=store, local_dir_use_symlinks=False)
    snapshot_download("stable-diffusion-v1-5/stable-diffusion-v1-5", local_dir=f"{store}/stable-diffusion-v1-5",
                      local_dir_use_symlinks=False,
                      allow_patterns=["model_index.json", "feature_extractor/*", "unet/config.json",
                                      "unet/diffusion_pytorch_model.bin", "v1-inference.yaml"])
    snapshot_download("stabilityai/sd-vae-ft-mse", local_dir=f"{store}/sd-vae-ft-mse", local_dir_use_symlinks=False)
    # The official source (lambdalabs/sd-image-variations-diffusers) was an empty repo on
    # 2026-11-14; BadToBest/EchoMimic mirrors the same image_encoder folder.
    snapshot_download("BadToBest/EchoMimic", local_dir=f"{store}/_img", local_dir_use_symlinks=False,
                      allow_patterns=["sd-image-variations-diffusers/image_encoder/*"])
    if not os.path.exists(f"{store}/image_encoder"):
        os.rename(f"{store}/_img/sd-image-variations-diffusers/image_encoder", f"{store}/image_encoder")
    snapshot_download("facebook/wav2vec2-base-960h", local_dir=f"{store}/wav2vec2-base-960h",
                      local_dir_use_symlinks=False,
                      allow_patterns=["*.json", "pytorch_model.bin", "*.txt"])
    open(f"{store}/.complete", "w").write("ok")
    models_vol.commit()


@app.function(image=image, gpu="A10G", volumes={MODELS: models_vol, DATA: data_vol}, timeout=5400)
def run_aniportrait(portrait: str = "poc/inputs/portrait.png", audio: str = "poc/inputs/audio.wav",
                    tag: str = "default", steps: int = 25, size: int = 512, accelerate: bool = True) -> dict:
    import glob
    import os
    import shutil
    import sys

    import yaml

    sys.path.insert(0, "/root")
    import _bench

    store = f"{MODELS}/aniportrait"
    _weights(store)
    link = f"{REPO}/pretrained_model"
    if os.path.islink(link) or os.path.isdir(link):
        if not os.path.islink(link):
            shutil.rmtree(link)
    if not os.path.exists(link):
        os.symlink(store, link)

    cfg = yaml.safe_load(open(f"{REPO}/configs/prompts/animation_audio.yaml"))
    cfg["test_cases"] = {f"{DATA}/{portrait}": [f"{DATA}/{audio}"]}
    cfg_path = f"/tmp/aniportrait_{tag}.yaml"
    yaml.safe_dump(cfg, open(cfg_path, "w"))
    shutil.rmtree(f"{REPO}/output", ignore_errors=True)

    cmd = ["python", "-m", "scripts.audio2vid", "--config", cfg_path, "-W", str(size), "-H", str(size),
           "--steps", str(steps)]
    if accelerate:
        cmd.append("-acc")
    cli = _bench.run_cli(cmd, cwd=REPO)
    out_dir = f"{DATA}/poc/outputs/aniportrait"
    os.makedirs(out_dir, exist_ok=True)
    out_path = None
    mp4s = [p for p in glob.glob(f"{REPO}/output/**/*.mp4", recursive=True) if not p.endswith("_noaudio.mp4")]
    mp4s = mp4s or glob.glob(f"{REPO}/output/**/*.mp4", recursive=True)
    if mp4s:
        out_path = f"{out_dir}/{tag}.mp4"
        shutil.copy(sorted(mp4s)[-1], out_path)
    res = _bench.summarize("aniportrait", cli, out_path, f"{DATA}/{audio}",
                           {"commit": COMMIT, "steps": steps, "size": size, "frame_interpolation": accelerate,
                            "note": "the output video is a grid: reference | pose | generated"})
    with open(f"{out_dir}/{tag}.json", "w") as f:
        json.dump(res, f, indent=1)
    data_vol.commit()
    return res


@app.local_entrypoint()
def main(tag: str = "default", steps: int = 25, size: int = 512):
    print(json.dumps(run_aniportrait.remote(tag=tag, steps=steps, size=size), indent=1))
