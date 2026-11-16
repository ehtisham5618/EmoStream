"""Shared Modal objects for the EmoStream GPU apps: volumes, the engine image, checkpoints.

Apps import this module and ship it with ``engine_image`` (see ``add_local_python_source``).
"""
from __future__ import annotations

from pathlib import Path

import modal

DITTO_COMMIT = "c3e47ee"
MODELS = "/models"
DATA = "/data"
MEAD = "/mead"
REPO = "/opt/ditto"
ROOT = Path(__file__).resolve().parents[2] if modal.is_local() else Path("/root")

models_vol = modal.Volume.from_name("emostream-v2-models", create_if_missing=True)
data_vol = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)
mead_raw = modal.Volume.from_name("emostream-mead-raw").read_only()

_NV = "/usr/local/lib/python3.10/site-packages/nvidia"
_base = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1",
                 index_url="https://download.pytorch.org/whl/cu121")
    .pip_install(
        "numpy==1.26.4", "onnxruntime-gpu==1.20.2", "mediapipe==0.10.14", "librosa==0.10.2.post1", "tqdm",
        "filetype", "imageio==2.36.1", "imageio-ffmpeg==0.5.1", "opencv-python-headless==4.10.0.84",
        "scikit-image", "cython==3.0.11", "colored", "einops", "scipy", "huggingface_hub", "soundfile",
        "pyyaml",
    )
    .run_commands(f"git clone https://github.com/antgroup/ditto-talkinghead {REPO}",
                  f"cd {REPO} && git checkout {DITTO_COMMIT}")
    .env({
        "LD_LIBRARY_PATH": ":".join(f"{_NV}/{d}/lib" for d in (
            "cudnn", "cublas", "cuda_runtime", "cufft", "curand", "cuda_nvrtc", "nvjitlink", "cusparse", "cusolver")),
        "DITTO_REPO": REPO, "PYTHONPATH": "/root",
    })
)


# TensorRT 8.6 links against cuDNN 8, so the TensorRT variant uses torch 2.1 (cuDNN 8.9).
_base_trt = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.1.2", "torchvision==0.16.2", index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("tensorrt==8.6.1", "cuda-python==12.2.1", "polygraphy", "colored",
                 extra_index_url="https://pypi.nvidia.com")
    .pip_install(
        "numpy==1.26.4", "onnxruntime-gpu==1.17.1", "mediapipe==0.10.14", "librosa==0.10.2.post1", "tqdm",
        "filetype", "imageio==2.36.1", "imageio-ffmpeg==0.5.1", "opencv-python-headless==4.10.0.84",
        "scikit-image", "cython==3.0.11", "einops", "scipy", "huggingface_hub", "soundfile", "pyyaml",
    )
    .run_commands(f"git clone https://github.com/antgroup/ditto-talkinghead {REPO}",
                  f"cd {REPO} && git checkout {DITTO_COMMIT}")
    .env({"DITTO_REPO": REPO, "PYTHONPATH": "/root"})
)


def engine_image(extra_pip: tuple[str, ...] = (), tensorrt: bool = False, env: dict | None = None,
                 local_dirs: tuple[tuple[str, str], ...] = ()) -> modal.Image:
    """Engine image. Build steps (pip, env) must come before local files are attached,
    so everything is assembled here in the right order."""
    img = _base_trt if tensorrt else _base
    if extra_pip:
        img = img.pip_install(*extra_pip)
    if env:
        img = img.env(env)
    img = (
        img.add_local_file(str(ROOT / "modal" / "apps" / "_bench.py"), "/root/_bench.py")
        .add_local_file(str(ROOT / "modal" / "apps" / "_common.py"), "/root/_common.py")
        .add_local_dir(str(ROOT / "emostream"), "/root/emostream")
    )
    for src, dst in local_dirs:
        img = img.add_local_dir(src, dst)
    return img


def ensure_checkpoints(tensorrt: bool = False) -> str:
    import os

    from huggingface_hub import snapshot_download

    dst = f"{MODELS}/ditto"
    if tensorrt and not os.path.exists(f"{dst}/ditto_trt_Ampere_Plus/hubert_fp32.engine"):
        snapshot_download("digital-avatar/ditto-talkinghead", local_dir=dst,
                          allow_patterns=["ditto_trt_Ampere_Plus/*"])
        models_vol.commit()
    lp = f"{MODELS}/liveportrait/stitching_retargeting_module.pth"
    if not os.path.exists(lp):  # LivePortrait lip-retargeting weights (MIT), 2 MB
        from huggingface_hub import hf_hub_download

        os.makedirs(os.path.dirname(lp), exist_ok=True)
        src = hf_hub_download("KlingTeam/LivePortrait",
                              "liveportrait/retargeting_models/stitching_retargeting_module.pth")
        import shutil

        shutil.copy(src, lp)
        models_vol.commit()
    if not os.path.exists(f"{dst}/ditto_pytorch/models/lmdm_v0.4_hubert.pth"):
        snapshot_download("digital-avatar/ditto-talkinghead", local_dir=dst,
                          allow_patterns=["ditto_cfg/*", "ditto_pytorch/**"])
        models_vol.commit()
    return dst
