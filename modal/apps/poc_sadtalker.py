"""Proof of concept: SadTalker (OpenTalker/SadTalker) on a Modal GPU.

Runs the repository's own ``inference.py`` with the released v0.0.2 checkpoints
on the shared test portrait and audio.

    modal run modal/apps/poc_sadtalker.py
    modal run modal/apps/poc_sadtalker.py --size 512 --tag s512
"""
from __future__ import annotations

import json
from pathlib import Path

import modal

COMMIT = "cd4c046"
MODELS = "/models"
DATA = "/data"
REPO = "/opt/SadTalker"

app = modal.App("emostream-v2-poc-sadtalker")
models_vol = modal.Volume.from_name("emostream-v2-models", create_if_missing=True)
data_vol = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "wget", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.0.1", "torchvision==0.15.2", "torchaudio==2.0.2",
                 index_url="https://download.pytorch.org/whl/cu118")
    .pip_install(
        "numpy==1.23.5", "face_alignment==1.3.5", "imageio==2.19.3", "imageio-ffmpeg==0.4.7",
        "librosa==0.9.2", "numba", "resampy==0.3.1", "pydub==0.25.1", "scipy==1.10.1", "kornia==0.6.8",
        "tqdm", "yacs==0.1.8", "pyyaml", "joblib==1.1.0", "scikit-image==0.19.3", "basicsr==1.4.2",
        "facexlib==0.3.0", "gfpgan", "av", "safetensors",
    )
    .run_commands(f"git clone https://github.com/OpenTalker/SadTalker {REPO}", f"cd {REPO} && git checkout {COMMIT}")
    .add_local_file(str(Path(__file__).parent / "_bench.py"), "/root/_bench.py")
)

URLS = {
    "checkpoints/mapping_00109-model.pth.tar": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00109-model.pth.tar",
    "checkpoints/mapping_00229-model.pth.tar": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00229-model.pth.tar",
    "checkpoints/SadTalker_V0.0.2_256.safetensors": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors",
    "checkpoints/SadTalker_V0.0.2_512.safetensors": "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_512.safetensors",
    "gfpgan/weights/alignment_WFLW_4HG.pth": "https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth",
    "gfpgan/weights/detection_Resnet50_Final.pth": "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
}


@app.function(image=image, gpu="L4", volumes={MODELS: models_vol, DATA: data_vol}, timeout=2400)
def run_sadtalker(portrait: str = "poc/inputs/portrait.png", audio: str = "poc/inputs/audio.wav",
                  tag: str = "s256", size: int = 256, still: bool = False, preprocess: str = "crop") -> dict:
    import glob
    import os
    import re
    import shutil
    import subprocess
    import sys

    sys.path.insert(0, "/root")
    import _bench

    store = f"{MODELS}/sadtalker"
    for rel, url in URLS.items():
        dst = f"{store}/{rel}"
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            subprocess.run(["wget", "-q", url, "-O", dst], check=True)
    models_vol.commit()
    for d in ("checkpoints", "gfpgan"):
        link = f"{REPO}/{d}"
        if not os.path.exists(link):
            os.symlink(f"{store}/{d}", link)

    out_dir = f"{DATA}/poc/outputs/sadtalker"
    work = f"/tmp/sadtalker_{tag}"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    cmd = ["python", "inference.py", "--driven_audio", f"{DATA}/{audio}", "--source_image", f"{DATA}/{portrait}",
           "--result_dir", work, "--size", str(size), "--preprocess", preprocess]
    if still:
        cmd.append("--still")
    cli = _bench.run_cli(cmd, cwd=REPO)
    out_path = None
    mp4s = sorted(glob.glob(f"{work}/*.mp4"))
    if mp4s:
        out_path = f"{out_dir}/{tag}.mp4"
        shutil.copy(mp4s[-1], out_path)
    # tqdm reports the face-render loop speed in batches/s (batch size 2 by default).
    m = re.findall(r"Face Renderer:.*?\|\s*(\d+)/(\d+)\s*\[([\d:]+)<", cli["log_tail"])
    res = _bench.summarize("sadtalker", cli, out_path, f"{DATA}/{audio}",
                           {"commit": COMMIT, "size": size, "still": still, "preprocess": preprocess,
                            "face_renderer_progress": m[-1] if m else None})
    with open(f"{out_dir}/{tag}.json", "w") as f:
        json.dump(res, f, indent=1)
    data_vol.commit()
    return res


@app.local_entrypoint()
def main(tag: str = "s256", size: int = 256, still: bool = False, preprocess: str = "crop"):
    res = run_sadtalker.remote(tag=tag, size=size, still=still, preprocess=preprocess)
    print(json.dumps(res, indent=1))
