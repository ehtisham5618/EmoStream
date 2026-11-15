"""Proof of concept: Ditto (antgroup/ditto-talkinghead, Apache-2.0) on a Modal GPU.

One static portrait + one audio file -> talking-head MP4, using the real released
PyTorch checkpoints. Measures wall time, FPS and GPU memory.

    modal run modal/apps/poc_ditto.py                      # offline mode, neutral
    modal run modal/apps/poc_ditto.py --online             # chunked streaming mode
    modal run modal/apps/poc_ditto.py --emo 3 --tag happy  # emotion index

Emotion indices (from the Ditto source, condition_handler.py):
    0 Angry, 1 Disgust, 2 Fear, 3 Happy, 4 Neutral, 5 Sad, 6 Surprise, 7 Contempt
"""
from __future__ import annotations

import json

import modal

DITTO_COMMIT = "c3e47ee"
MODELS = "/models"
DATA = "/data"
REPO = "/opt/ditto"

app = modal.App("emostream-v2-poc-ditto")
models_vol = modal.Volume.from_name("emostream-v2-models", create_if_missing=True)
data_vol = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)

_NV = "/usr/local/lib/python3.10/site-packages/nvidia"
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1",
        index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "numpy==1.26.4", "onnxruntime-gpu==1.20.2", "mediapipe==0.10.14",
        "librosa==0.10.2.post1", "tqdm", "filetype", "imageio==2.36.1", "imageio-ffmpeg==0.5.1",
        "opencv-python-headless==4.10.0.84", "scikit-image", "cython==3.0.11", "colored",
        "einops", "scipy", "huggingface_hub", "nvidia-ml-py",
    )
    .run_commands(
        f"git clone https://github.com/antgroup/ditto-talkinghead {REPO}",
        f"cd {REPO} && git checkout {DITTO_COMMIT}",
    )
    .env({
        "LD_LIBRARY_PATH": ":".join(
            f"{_NV}/{d}/lib" for d in
            ("cudnn", "cublas", "cuda_runtime", "cufft", "curand", "cuda_nvrtc", "nvjitlink", "cusparse", "cusolver")
        ),
        "HF_HUB_ENABLE_HF_TRANSFER": "0",
    })
)


class GpuMeter:
    """Polls NVML for whole-device memory (covers PyTorch + ONNX Runtime)."""

    def __init__(self, interval=0.2):
        import threading

        import pynvml

        pynvml.nvmlInit()
        self._nv = pynvml
        self._h = pynvml.nvmlDeviceGetHandleByIndex(0)
        self.name = pynvml.nvmlDeviceGetName(self._h)
        self.peak = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._t.start()

    def _loop(self, interval):
        while not self._stop.is_set():
            used = self._nv.nvmlDeviceGetMemoryInfo(self._h).used
            self.peak = max(self.peak, used)
            self._stop.wait(interval)

    def reset(self):
        self.peak = 0

    def stop(self):
        self._stop.set()
        self._t.join()


def _ensure_checkpoints() -> str:
    import os

    from huggingface_hub import snapshot_download

    dst = f"{MODELS}/ditto"
    marker = f"{dst}/ditto_pytorch/models/lmdm_v0.4_hubert.pth"
    if not os.path.exists(marker):
        snapshot_download(
            "digital-avatar/ditto-talkinghead", local_dir=dst,
            allow_patterns=["ditto_cfg/*", "ditto_pytorch/**"],
        )
        models_vol.commit()
    return dst


@app.function(image=image, gpu=["L4", "A10G", "T4"], volumes={MODELS: models_vol, DATA: data_vol}, timeout=1800)
def run_ditto(
    portrait: str = "poc/inputs/portrait.png",
    audio: str = "poc/inputs/audio.wav",
    tag: str = "neutral",
    emo: int = 4,
    online: bool = False,
    sampling_timesteps: int = 50,
    repeats: int = 2,
) -> dict:
    import os
    import subprocess
    import sys
    import time

    import torch

    sys.path.insert(0, REPO)
    os.chdir(REPO)
    ckpt = _ensure_checkpoints()
    meter = GpuMeter()

    t0 = time.perf_counter()
    if online:
        from stream_pipeline_online import StreamSDK
    else:
        from stream_pipeline_offline import StreamSDK
    import inference as ditto_inference
    import librosa

    sdk = StreamSDK(f"{ckpt}/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl", f"{ckpt}/ditto_pytorch")
    load_s = time.perf_counter() - t0

    src = f"{DATA}/{portrait}"
    wav = f"{DATA}/{audio}"
    out_dir = f"{DATA}/poc/outputs/ditto"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/{tag}.mp4"

    dur = librosa.get_duration(path=wav)
    setup_kwargs = {"emo": emo, "sampling_timesteps": sampling_timesteps}
    if online:
        setup_kwargs["online_mode"] = True
    runs = []
    for i in range(repeats):
        torch.cuda.reset_peak_memory_stats()
        meter.reset()
        t = time.perf_counter()
        ditto_inference.run(sdk, wav, src, out_path, more_kwargs={"setup_kwargs": setup_kwargs, "run_kwargs": {}})
        wall = time.perf_counter() - t
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
             "stream=nb_read_frames,width,height,r_frame_rate", "-of", "json", out_path],
            capture_output=True, text=True,
        )
        v = json.loads(probe.stdout)["streams"][0]
        n = int(v["nb_read_frames"])
        runs.append({
            "run": i, "wall_s": round(wall, 3), "frames": n, "fps_end_to_end": round(n / wall, 2),
            "realtime_factor": round(wall / dur, 3),
            "width": v["width"], "height": v["height"], "frame_rate": v["r_frame_rate"],
            "torch_peak_alloc_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
            "torch_peak_reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 3),
            "device_peak_used_gib": round(meter.peak / 2**30, 3),
        })
    meter.stop()
    result = {
        "model": "ditto", "commit": DITTO_COMMIT, "backend": "pytorch", "mode": "online" if online else "offline",
        "gpu": meter.name, "emo": emo, "sampling_timesteps": sampling_timesteps,
        "audio_s": round(dur, 3), "model_load_s": round(load_s, 2), "runs": runs, "output": out_path,
        "note": "wall_s includes portrait registration, audio features, motion diffusion, rendering and "
                "MP4 encoding; run 0 includes warm-up.",
    }
    with open(f"{out_dir}/{tag}.json", "w") as f:
        json.dump(result, f, indent=1)
    data_vol.commit()
    return result


@app.local_entrypoint()
def main(tag: str = "neutral", emo: int = 4, online: bool = False, sampling_timesteps: int = 50,
         portrait: str = "poc/inputs/portrait.png", audio: str = "poc/inputs/audio.wav"):
    res = run_ditto.remote(portrait=portrait, audio=audio, tag=tag, emo=emo, online=online,
                           sampling_timesteps=sampling_timesteps)
    print(json.dumps(res, indent=1))


@app.function(image=image, volumes={MODELS: models_vol}, timeout=600)
def dump_cfg() -> dict:
    """Prints the released Ditto config pickles (offline / online / pytorch) as plain data."""
    import glob
    import pickle

    import numpy as np

    ckpt = _ensure_checkpoints()

    def plain(v):
        if isinstance(v, np.ndarray):
            return f"ndarray{v.shape}"
        if isinstance(v, dict):
            return {str(k): plain(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [plain(x) for x in v][:12]
        return v if isinstance(v, (int, float, str, bool, type(None))) else str(type(v))

    out = {}
    for p in sorted(glob.glob(f"{ckpt}/ditto_cfg/*.pkl")):
        with open(p, "rb") as f:
            out[p.split("/")[-1]] = plain(pickle.load(f))
    return out


@app.local_entrypoint()
def cfg():
    print(json.dumps(dump_cfg.remote(), indent=1))
