"""Proof of concept: Hallo2 (fudan-generative-vision/hallo2, MIT) on a Modal GPU.

Runs the repository's own ``scripts/inference_long.py`` with the released weights
on the shared test portrait and audio. This is a latent-diffusion video model
(Stable Diffusion 1.5 backbone, 40 DDIM steps by default), so it is expected to
be far slower than real time; the run measures by how much.

    modal run modal/apps/poc_hallo2.py
"""
from __future__ import annotations

import json
from pathlib import Path

import modal

COMMIT = "58a9aa6"
MODELS = "/models"
DATA = "/data"
REPO = "/opt/hallo2"

app = modal.App("emostream-v2-poc-hallo2")
models_vol = modal.Volume.from_name("emostream-v2-models", create_if_missing=True)
data_vol = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.2.2", "torchvision==0.17.2", "torchaudio==2.2.2",
                 index_url="https://download.pytorch.org/whl/cu121")
    .pip_install(
        "accelerate==0.28.0", "audio-separator==0.17.2", "av==12.1.0", "bitsandbytes==0.43.1",
        "decord==0.6.0", "diffusers==0.32.2", "einops==0.8.0", "ffmpeg-python==0.2.0", "icecream==2.1.3",
        "insightface==0.7.3", "librosa==0.10.2.post1", "lpips==0.1.4", "mediapipe==0.10.14",
        "moviepy==1.0.3", "numpy==1.26.4", "omegaconf==2.3.0", "onnx2torch==1.5.14", "onnx==1.16.1",
        "onnxruntime-gpu==1.18.0", "opencv-python-headless==4.9.0.80", "pillow==10.3.0",
        "setuptools==70.0.0", "tqdm==4.66.4", "transformers==4.39.2", "xformers==0.0.25.post1",
        "huggingface_hub==0.25.2", "scipy", "pyyaml",
    )
    .run_commands(f"git clone https://github.com/fudan-generative-vision/hallo2 {REPO}",
                  f"cd {REPO} && git checkout {COMMIT}")
    .add_local_file(str(Path(__file__).parent / "_bench.py"), "/root/_bench.py")
)


@app.function(image=image, gpu="A10G", volumes={MODELS: models_vol, DATA: data_vol}, timeout=5400)
def run_hallo2(portrait: str = "poc/inputs/portrait.png", audio: str = "poc/inputs/audio.wav",
               tag: str = "default", steps: int = 40) -> dict:
    import glob
    import os
    import shutil
    import subprocess
    import sys

    import yaml
    from huggingface_hub import snapshot_download

    sys.path.insert(0, "/root")
    import _bench

    store = f"{MODELS}/hallo2"
    if not os.path.exists(f"{store}/hallo2/net.pth"):
        snapshot_download("fudan-generative-ai/hallo2", local_dir=store,
                          ignore_patterns=["realesrgan/*", "CodeFormer/*", "*.md"])
        models_vol.commit()
    link = f"{REPO}/pretrained_models"
    if not os.path.exists(link):
        os.symlink(store, link)

    work = f"/tmp/hallo2_{tag}"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    # Hallo2 names its output folder after the image stem; give it a square PNG copy.
    src = f"{work}/portrait.png"
    shutil.copy(f"{DATA}/{portrait}", src)
    cfg = yaml.safe_load(open(f"{REPO}/configs/inference/long.yaml"))
    cfg.update({"source_image": src, "driving_audio": f"{DATA}/{audio}", "save_path": f"{work}/out/",
                "cache_path": f"{work}/cache", "inference_steps": steps})
    cfg_path = f"{work}/long.yaml"
    yaml.safe_dump(cfg, open(cfg_path, "w"))

    cli = _bench.run_cli(["python", "scripts/inference_long.py", "--config", cfg_path], cwd=REPO,
                         env={"PYTHONPATH": REPO})
    out_dir = f"{DATA}/poc/outputs/hallo2"
    os.makedirs(out_dir, exist_ok=True)
    out_path = None
    merged = glob.glob(f"{work}/out/**/merge_video.mp4", recursive=True) + glob.glob(f"{work}/out/merge_video.mp4")
    if merged:
        out_path = f"{out_dir}/{tag}.mp4"
        # Mux the driving audio so the clip can be judged for lip sync.
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", merged[0], "-i", f"{DATA}/{audio}",
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", out_path],
                       check=False)
        if not os.path.exists(out_path):
            shutil.copy(merged[0], out_path)
    res = _bench.summarize("hallo2", cli, out_path, f"{DATA}/{audio}", {"commit": COMMIT, "inference_steps": steps})
    with open(f"{out_dir}/{tag}.json", "w") as f:
        json.dump(res, f, indent=1)
    data_vol.commit()
    return res


@app.local_entrypoint()
def main(tag: str = "default", steps: int = 40):
    print(json.dumps(run_hallo2.remote(tag=tag, steps=steps), indent=1))
